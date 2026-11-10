from django.contrib import admin, messages
from import_export.admin import ImportMixin
from unfold.admin import ModelAdmin, TabularInline
from unfold.contrib.import_export.forms import ImportForm

from . import services
from .importing import MCQResource
from .models import Question, QuestionVersion


class VersionInline(TabularInline):
    """Versions are history: visible, never editable, never deleted (CLAUDE.md)."""

    model = QuestionVersion
    extra = 0
    fields = ("version", "content_hash", "created_at")
    readonly_fields = fields
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(Question)
class QuestionAdmin(ImportMixin, ModelAdmin):
    resource_classes = [MCQResource]
    import_form_class = ImportForm
    list_display = ("stable_id", "module", "format", "pool", "status", "tags", "has_hint")
    list_filter = ("module", "pool", "status", "format")
    search_fields = ("stable_id",)
    inlines = [VersionInline]
    actions = ["publish_selected", "retire_selected"]

    def get_queryset(self, request):
        """Final-pool questions are admin-only here too (§5)."""
        from apps.accounts.rules import can_access_final_pool

        qs = super().get_queryset(request)
        return qs if can_access_final_pool(request.user) else qs.exclude(pool="final")

    @admin.display(boolean=True, description="Hint")
    def has_hint(self, obj):
        version = obj.current_version
        return bool(version and version.body.get("hint"))

    @admin.action(description="Publish selected (needs a hint, a PC tag and a pool)")
    def publish_selected(self, request, queryset):
        done = 0
        for question in queryset:
            try:
                services.publish(question)
                done += 1
            except services.PublishError as exc:
                self.message_user(request, f"{question.stable_id}: {exc}", messages.WARNING)
        if done:
            self.message_user(request, f"{done} question(s) are now live.", messages.SUCCESS)

    @admin.action(description="Retire selected")
    def retire_selected(self, request, queryset):
        for question in queryset:
            services.retire(question)
