"""Translations in the admin: the review list, the per-module XLSX sheets and coverage (§14)."""

from collections import Counter

from django import forms
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from unfold.admin import ModelAdmin

from apps.content.models import Module

from . import keys, rules, xlsx
from .models import TRANSLATED_LANGUAGES, Translation, TranslationStatus
from .sources import course_sources, sources_by_key


class SheetForm(forms.Form):
    module = forms.TypedChoiceField(coerce=int, label="Module")
    file = forms.FileField(label="Translation sheet (.xlsx, up to 5 MB)")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["module"].choices = [
            (m.number, f"Module {m.number}: {m.display_title}") for m in Module.objects.all()
        ]


class TranslationForm(forms.ModelForm):
    class Meta:
        model = Translation
        fields = ("text",)
        widgets = {"text": forms.Textarea(attrs={"rows": 4})}

    def clean_text(self):
        text = " ".join(self.cleaned_data["text"].split())
        errors = xlsx.line_errors(self.instance.source_text, text)
        if errors:
            raise forms.ValidationError("; ".join(errors))
        return text


@admin.register(Translation)
class TranslationAdmin(ModelAdmin):
    form = TranslationForm
    list_display = ("key", "language", "status", "short_text", "origin", "uploaded_by")
    list_filter = ("language", "status", "origin")
    search_fields = ("key", "text", "source_text")
    readonly_fields = (
        "key",
        "language",
        "source_text",
        "status",
        "origin",
        "uploaded_by",
        "reviewed_by",
        "reviewed_at",
    )
    fields = ("key", "language", "source_text", "text", *readonly_fields[3:])
    actions = ["mark_reviewed"]
    list_per_page = 50

    @admin.display(description="Translation")
    def short_text(self, obj):
        return obj.text[:80]

    def has_add_permission(self, request):
        return False  # lines come from a sheet; see "Translation sheets"

    def has_change_permission(self, request, obj=None):
        return rules.can_upload(request.user)

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        """An edit in the admin is a new draft by this user, like an upload."""
        rules.save_line(
            key=obj.key,
            language=obj.language,
            text=form.cleaned_data["text"],
            english=Translation.objects.get(pk=obj.pk).source_text,
            user=request.user,
            origin="admin",
        )

    @admin.action(description="Mark selected lines reviewed")
    def mark_reviewed(self, request, queryset):
        current = sources_by_key()
        done, refused = 0, Counter()
        for row in queryset:
            source = current.get(row.key)
            reason = rules.review_refusal(request.user, row, source.english if source else None)
            if reason:
                refused[reason] += 1
                continue
            rules.mark_reviewed(request.user, row, source.english, request)
            done += 1
        if done:
            messages.success(request, f"{done} line(s) marked reviewed.")
        for reason, count in refused.items():
            messages.warning(request, f"{count} line(s) not reviewed: {reason}")

    def changelist_view(self, request, extra_context=None):
        extra_context = {
            **(extra_context or {}),
            "sheets_url": reverse("admin:translations_sheets"),
        }
        return super().changelist_view(request, extra_context)

    def get_urls(self):
        return [
            path(
                "sheets/",
                self.admin_site.admin_view(self.sheets_view),
                name="translations_sheets",
            ),
            path(
                "sheets/<int:number>.xlsx",
                self.admin_site.admin_view(self.export_view),
                name="translations_export",
            ),
            *super().get_urls(),
        ]

    def export_view(self, request, number):
        if not self.has_view_permission(request):
            raise PermissionDenied
        data = xlsx.export_module(number)
        response = HttpResponse(
            data,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response["Content-Disposition"] = (
            f'attachment; filename="translations-module-{number}.xlsx"'
        )
        return response

    def sheets_view(self, request):
        """Download a module's sheet, upload it back, and see coverage per language."""
        if not self.has_view_permission(request):
            raise PermissionDenied
        form = SheetForm(request.POST or None, request.FILES or None)
        if request.method == "POST":
            if not rules.can_upload(request.user):
                raise PermissionDenied
            if form.is_valid():
                try:
                    result = xlsx.import_module(
                        form.cleaned_data["module"],
                        form.cleaned_data["file"],
                        request.user,
                        request,
                    )
                except xlsx.SheetRejected as exc:
                    for error in exc.errors[:30]:
                        form.add_error(None, error)
                    if len(exc.errors) > 30:
                        form.add_error(None, f"… and {len(exc.errors) - 30} more problems.")
                else:
                    messages.success(
                        request,
                        f"Saved as drafts: {result.created} new, {result.changed} changed, "
                        f"{result.same} unchanged. {result.stale} line(s) were translated from "
                        "older English and show as stale.",
                    )
                    return redirect("admin:translations_sheets")
        context = {
            **self.admin_site.each_context(request),
            "title": "Translation sheets",
            "form": form,
            "can_upload": rules.can_upload(request.user),
            "coverage": coverage(),
            "languages": TRANSLATED_LANGUAGES,
        }
        return TemplateResponse(request, "admin/translations/sheets.html", context)


def coverage() -> list[dict]:
    """Per module and language: reviewed, draft, stale and missing lines (§15 coverage)."""
    sources = course_sources()
    rows = {(r.key, r.language): r for r in Translation.objects.all().only(
        "key", "language", "source_hash", "status"
    )}  # fmt: skip
    table = {}
    for source in sources:
        entry = table.setdefault(
            source.module,
            {
                "module": source.module,
                "total": 0,
                "url": reverse("admin:translations_export", args=[source.module]),
                **{code: Counter() for code in TRANSLATED_LANGUAGES},
            },
        )
        entry["total"] += 1
        digest = keys.source_hash(source.english)
        for code in TRANSLATED_LANGUAGES:
            row = rows.get((source.key, code))
            if row is None:
                entry[code]["missing"] += 1
            elif row.source_hash != digest:
                entry[code]["stale"] += 1
            elif row.status == TranslationStatus.REVIEWED:
                entry[code]["reviewed"] += 1
            else:
                entry[code]["draft"] += 1
    return [table[k] for k in sorted(table, key=lambda n: (n is None, n))]
