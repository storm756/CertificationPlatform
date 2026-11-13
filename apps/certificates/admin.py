"""Certificates in the admin (Stage 6 left "approve, revoke" for Stage 7). Admins only.

Nothing here edits a certificate: it is a snapshot. Revoking and removing holder details go
through apps/certificates/services.py, which checks the role and writes the audit log.
"""

from django import forms
from django.contrib import admin, messages
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import reverse
from unfold.admin import ModelAdmin

from apps.audit.services import audit

from . import services
from .models import Certificate, CertificateSettings


class AdminOnlyMixin:
    def has_module_permission(self, request):
        return services.is_admin(request.user)

    def has_view_permission(self, request, obj=None):
        return services.is_admin(request.user)

    def has_delete_permission(self, request, obj=None):
        return False


class RevokeForm(forms.Form):
    reason = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text="Kept on the certificate for the record. The verify page shows only 'Revoked'.",
    )
    allow_reissue = forms.BooleanField(
        required=False,
        label="Allow a new certificate (for example to correct the printed name)",
        help_text="Leave unticked to block a new certificate for this learner. A new certificate "
        "always gets a new number.",
    )


class EraseForm(forms.Form):
    confirm = forms.BooleanField(
        label="The holder asked for their details to be removed. Remove the name and delete the PDF.",
    )


@admin.register(Certificate)
class CertificateAdmin(AdminOnlyMixin, ModelAdmin):
    list_display = ("certificate_no", "holder", "status", "issued_at", "auto_issued", "batch_code")
    list_filter = ("status", "auto_issued")
    search_fields = ("certificate_no", "user__email")
    ordering = ("-serial",)
    actions = ["revoke_selected", "erase_holder_selected"]
    readonly_fields = (
        "certificate_no", "holder", "user", "status", "verify_code", "issued_at", "issued_by",
        "auto_issued", "revoked_at", "revoked_by", "revoked_reason", "reissue_allowed",
        "holder_erased_at", "pdf_sha256", "snapshot",
    )  # fmt: skip
    fields = readonly_fields

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    @admin.display(description="Holder")
    def holder(self, obj):
        return obj.holder_name or "(removed at the holder's request)"

    @admin.display(description="Batch")
    def batch_code(self, obj):
        return (obj.snapshot.get("batch") or {}).get("code", "")

    def changelist_view(self, request, extra_context=None):
        if request.method == "GET":
            for warning in services.issue_warnings():
                self.message_user(request, warning, messages.WARNING)
        return super().changelist_view(request, extra_context)

    def _confirm(self, request, queryset, *, action, form, title, text, button):
        return TemplateResponse(
            request,
            "admin/certificates/confirm_action.html",
            {
                **self.admin_site.each_context(request),
                "title": title,
                "text": text,
                "button": button,
                "form": form,
                "certificates": queryset,
                "action": action,
                "opts": self.model._meta,
            },
        )

    @admin.action(description="Revoke the selected certificates…")
    def revoke_selected(self, request, queryset):
        form = RevokeForm(request.POST if "apply" in request.POST else None)
        if form.is_valid():
            done = 0
            for cert in queryset:
                if cert.is_issued:
                    services.revoke(cert, request.user, form.cleaned_data["reason"], allow_reissue=form.cleaned_data["allow_reissue"], request=request)  # fmt: skip
                    done += 1
            self.message_user(request, f"{done} certificate(s) revoked. The verify page now shows 'Revoked'.", messages.SUCCESS)  # fmt: skip
            return None
        return self._confirm(
            request, queryset, action="revoke_selected", form=form,
            title="Revoke certificates",
            text="The verify page will show these certificates as revoked. This cannot be undone.",
            button="Revoke",
        )  # fmt: skip

    @admin.action(description="Remove holder details (erasure request)…")
    def erase_holder_selected(self, request, queryset):
        form = EraseForm(request.POST if "apply" in request.POST else None)
        if form.is_valid():
            for cert in queryset:
                services.erase_holder(cert, request.user, request=request)
            self.message_user(request, f"Holder details removed from {queryset.count()} certificate(s).", messages.SUCCESS)  # fmt: skip
            return None
        return self._confirm(
            request, queryset, action="erase_holder_selected", form=form,
            title="Remove holder details",
            text="The printed name and the PDF are deleted. The number, grade, dates and status stay, "
            "and the verify page says the holder's details were removed at their request. "
            "This cannot be undone.",
            button="Remove details",
        )  # fmt: skip


class CertificateSettingsForm(forms.ModelForm):
    class Meta:
        model = CertificateSettings
        fields = ["nsqf_approved", "nsqf_level", "nsqf_credits"]


@admin.register(CertificateSettings)
class CertificateSettingsAdmin(AdminOnlyMixin, ModelAdmin):
    """One row. NSQF wording for new certificates only; issued ones never change."""

    form = CertificateSettingsForm

    def has_add_permission(self, request):
        return services.is_admin(request.user) and not CertificateSettings.objects.exists()

    def has_change_permission(self, request, obj=None):
        return services.is_admin(request.user)

    def changelist_view(self, request, extra_context=None):
        obj = CertificateSettings.load()
        return redirect(reverse("admin:certificates_certificatesettings_change", args=[obj.pk]))

    def save_model(self, request, obj, form, change):
        obj.pk = 1
        super().save_model(request, obj, form, change)
        if form.changed_data:
            audit("certificate.settings_changed", actor=request.user, target=obj, request=request, fields=sorted(form.changed_data), nsqf_approved=obj.nsqf_approved)  # fmt: skip
