from django.contrib import admin, messages
from unfold.admin import ModelAdmin

from . import rules
from .models import AssessmentPart, Attempt, AttemptItem, ProgrammeAssessment


@admin.register(AssessmentPart)
class AssessmentPartAdmin(ModelAdmin):
    list_display = (
        "__str__",
        "family",
        "marks",
        "counted",
        "selection",
        "draw_n",
        "pool",
        "is_published",
    )
    list_filter = ("module", "family", "is_published")
    readonly_fields = ("is_published",)  # changed only by the actions below, which validate first
    actions = ["check_parts", "publish_parts", "unpublish_parts"]

    @admin.action(description="Check the selected parts (validate_part)")
    def check_parts(self, request, queryset):
        for part in queryset:
            errors = rules.validate_part(part)
            if errors:
                self.message_user(request, f"{part}: " + " ".join(errors), messages.WARNING)
            else:
                self.message_user(request, f"{part}: ready to publish.", messages.SUCCESS)

    @admin.action(description="Publish the selected parts")
    def publish_parts(self, request, queryset):
        for part in queryset:
            try:
                rules.publish_part(part, actor=request.user)
                self.message_user(request, f"{part} is published.", messages.SUCCESS)
            except rules.PartInvalid as exc:
                self.message_user(request, f"{part}: {exc}", messages.ERROR)

    @admin.action(description="Unpublish the selected parts")
    def unpublish_parts(self, request, queryset):
        for part in queryset:
            rules.unpublish_part(part, actor=request.user)


@admin.register(ProgrammeAssessment)
class ProgrammeAssessmentAdmin(ModelAdmin):
    list_display = ("kind", "cooldown_hours")


class ItemInline(admin.TabularInline):
    """Read-only. The option map and responses hold the key mapping, so they are not shown."""

    model = AttemptItem
    extra = 0
    fields = ("position", "question_version", "points", "score", "gate_flag")
    readonly_fields = fields
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Attempt)
class AttemptAdmin(ModelAdmin):
    list_display = (
        "user",
        "part",
        "number",
        "status",
        "score",
        "counted",
        "all_answered",
        "last_saved_at",
    )
    list_filter = ("status", "counted", "gate_breached")
    inlines = [ItemInline]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
