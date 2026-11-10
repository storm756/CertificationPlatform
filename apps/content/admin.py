from django import forms
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.html import format_html
from unfold.admin import ModelAdmin, TabularInline

from . import services
from .blocks import BlocksInvalid
from .docx import DocxRejected, docx_to_blocks
from .models import MediaAsset, Module, Unit, UnitVersion, VersionSource, VersionStatus


class DocxForm(forms.Form):
    file = forms.FileField(label="Word file (.docx, up to 10 MB)")


class VersionInline(TabularInline):
    """Versions are history: visible, never edited or deleted."""

    model = UnitVersion
    extra = 0
    fields = ("version", "title", "status", "source", "published_at")
    readonly_fields = fields
    can_delete = False
    ordering = ("-version",)

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(Module)
class ModuleAdmin(ModelAdmin):
    list_display = ("number", "title", "kind", "hours")
    readonly_fields = ("overview",)


@admin.register(Unit)
class UnitAdmin(ModelAdmin):
    list_display = ("module", "slug", "type", "nominal_minutes", "state", "upload")
    list_filter = ("module", "type")
    inlines = [VersionInline]

    @admin.display(description="Live version")
    def state(self, obj):
        live = obj.published()
        return f"v{live.version}" if live else "none"

    @admin.display(description="")
    def upload(self, obj):
        url = reverse("admin:content_unit_docx", args=[obj.pk])
        return format_html('<a href="{}">Upload Word file</a>', url)

    def get_urls(self):
        return [
            path(
                "<int:pk>/docx/",
                self.admin_site.admin_view(self.docx_view),
                name="content_unit_docx",
            ),
            *super().get_urls(),
        ]

    def docx_view(self, request, pk):
        """A Word file becomes a DRAFT version. It goes live only when someone publishes it."""
        unit = self.get_object(request, str(pk))
        if unit is None:
            raise Http404
        form = DocxForm(request.POST or None, request.FILES or None)
        if request.method == "POST" and form.is_valid():
            try:
                title, blocks, notes = docx_to_blocks(form.cleaned_data["file"])
                version = services.add_version(
                    unit, title or unit.slug, blocks, source=VersionSource.DOCX, author=request.user
                )
            except (DocxRejected, BlocksInvalid) as exc:
                form.add_error("file", str(exc))
            else:
                messages.success(
                    request, f"Draft version {version.version} created. Review it, then publish."
                )
                for note in notes[:3]:
                    messages.info(request, note)
                return redirect("admin:content_unit_change", unit.pk)
        context = {
            **self.admin_site.each_context(request),
            "title": "Upload a Word file",
            "form": form,
            "unit": unit,
        }
        return TemplateResponse(request, "admin/content/docx_upload.html", context)


@admin.register(UnitVersion)
class UnitVersionAdmin(ModelAdmin):
    list_display = ("unit", "version", "title", "status", "source", "author")
    list_filter = ("status", "source", "unit__module")
    readonly_fields = [f.name for f in UnitVersion._meta.fields]
    actions = ["publish_selected", "restore_selected"]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.action(description="Publish the selected drafts")
    def publish_selected(self, request, queryset):
        done = 0
        for version in queryset.filter(status=VersionStatus.DRAFT):
            try:
                services.publish(version, request.user, request=request)
                done += 1
            except PermissionDenied:
                self.message_user(
                    request, "Only an admin or a content publisher can publish.", messages.ERROR
                )
                return
        self.message_user(request, f"Published {done} version(s).")

    @admin.action(description="Restore the selected version (one at a time)")
    def restore_selected(self, request, queryset):
        if queryset.count() != 1:
            self.message_user(request, "Pick exactly one version to restore.", messages.ERROR)
            return
        try:
            services.restore(queryset.get(), request.user, request=request)
        except PermissionDenied:
            self.message_user(
                request, "Only an admin or a content publisher can restore.", messages.ERROR
            )
            return
        self.message_user(request, "Restored as a new published version.")


@admin.register(MediaAsset)
class MediaAssetAdmin(ModelAdmin):
    list_display = ("module", "kind", "title", "size")
    readonly_fields = [f.name for f in MediaAsset._meta.fields]

    def has_add_permission(self, request):
        return False
