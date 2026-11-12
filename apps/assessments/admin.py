from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from unfold.admin import ModelAdmin

from . import examsets, rules, services
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
        "max_attempts",
        "is_published",
    )
    list_filter = ("module", "family", "is_published")
    readonly_fields = ("is_published",)  # changed only by the actions below, which validate first
    actions = ["check_parts", "publish_parts", "unpublish_parts"]

    def save_model(self, request, obj, form, change):
        _save_with_audited_limit(request, obj, change)

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
    list_display = ("kind", "cooldown_hours", "max_attempts")

    def save_model(self, request, obj, form, change):
        _save_with_audited_limit(request, obj, change)


def _save_with_audited_limit(request, obj, change):
    """Save, and audit a change of the attempt limit (D32) in the same transaction."""
    with transaction.atomic():
        old = services.stored_max_attempts(obj)
        obj.save()
        services.audit_limit_change(obj, old, actor=request.user, request=request)


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
    """Membership only: which questions are in the paper, held in reserve or rejected. Rows are
    never deleted (question history stays) and a released set is read-only. Question text and keys
    live on the question, which is admin-only for the final pool."""

    model = ExamSetItem
    extra = 0
    fields = ("question", "in_pretest", "state")
    readonly_fields = ("question", "in_pretest")  # the pre-test selection comes from the import
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return obj is not None and not obj.is_released


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

    @admin.display(description="Questions in the paper")
    def item_count(self, obj):
        return obj.members().count()

    def save_model(self, request, obj, form, change):
        """Take the same row lock as import and release, and refuse a set that was released while
        this page was open."""
        locked = ExamSet.objects.select_for_update().get(pk=obj.pk)
        if locked.is_released:
            raise PermissionDenied("This set was released; it is fixed. Start a new draft set.")
        super().save_model(request, obj, form, change)

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
