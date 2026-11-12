from django.contrib import admin, messages
from unfold.admin import ModelAdmin

from . import examsets, rules
from .models import AssessmentPart, Attempt, AttemptItem, ExamSet, ExamSetItem, ProgrammeAssessment


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


class ExamSetItemInline(admin.TabularInline):
    """Membership only: question ids and the pre-test flag. Question text and keys live on the
    question, which is admin-only for the final pool."""

    model = ExamSetItem
    extra = 0
    fields = ("question", "in_pretest")
    readonly_fields = ("question", "in_pretest")  # membership is fixed by the import
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(ExamSet)
class ExamSetAdmin(ModelAdmin):
    list_display = ("code", "name", "status", "released_at", "item_count")
    readonly_fields = ("status", "released_at")
    inlines = [ExamSetItemInline]
    actions = ["check_sets", "release_sets"]

    @staticmethod
    def _admin(request):
        return request.user.is_superuser or request.user.role == "admin"

    def has_module_permission(self, request):
        return self._admin(request)

    def has_view_permission(self, request, obj=None):
        return self._admin(request)

    def has_change_permission(self, request, obj=None):
        return self._admin(request)

    def has_add_permission(self, request):
        return False  # sets are created by the private import (import_final_sets)

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description="Questions")
    def item_count(self, obj):
        return obj.items.count()

    @admin.action(description="Check the selected sets (release checks)")
    def check_sets(self, request, queryset):
        for exam_set in queryset:
            errors = examsets.release_errors(exam_set)
            level = messages.WARNING if errors else messages.SUCCESS
            text = f"{exam_set}: " + (" ".join(errors[:12]) + (f" (+{len(errors) - 12} more)" if len(errors) > 12 else "") if errors else "ready to release.")  # fmt: skip
            self.message_user(request, text, level)

    @admin.action(description="Release the selected sets (runs the checks first)")
    def release_sets(self, request, queryset):
        for exam_set in queryset:
            errors = examsets.release(exam_set, request.user, request)
            if errors:
                self.message_user(request, f"{exam_set} not released: {len(errors)} problem(s). Run the check for details.", messages.ERROR)  # fmt: skip
            else:
                self.message_user(request, f"{exam_set} released.", messages.SUCCESS)
