from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline

from .models import Batch, BatchMentor, Enrolment


class BatchMentorInline(TabularInline):
    model = BatchMentor
    extra = 0
    autocomplete_fields = ["mentor"]


@admin.register(Batch)
class BatchAdmin(ModelAdmin):
    list_display = (
        "code",
        "name",
        "centre",
        "accepting",
        "opens_at",
        "closes_at",
        "seat_limit",
        "status",
        "exam_set",
    )
    list_filter = ("accepting", "status", "is_open_pool", "exam_set")
    search_fields = ("code", "name", "centre")
    inlines = [BatchMentorInline]
    list_display_links = ("code",)

    # --- the final exam set (admin only; audited; only released sets can be chosen) ----------

    @staticmethod
    def _is_admin(request):
        return request.user.role == "admin" or request.user.is_superuser

    def get_readonly_fields(self, request, obj=None):
        fields = list(super().get_readonly_fields(request, obj))
        return fields if self._is_admin(request) else [*fields, "exam_set"]

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "exam_set":
            from apps.assessments.models import ExamSet, ExamSetStatus

            kwargs["queryset"] = ExamSet.objects.filter(status=ExamSetStatus.RELEASED)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        """Route an exam-set change through examsets.assign so it is checked and audited."""
        from apps.assessments import examsets

        new_set = obj.exam_set if "exam_set" in form.changed_data else None
        if change and "exam_set" in form.changed_data:
            obj.exam_set_id = type(obj).objects.get(pk=obj.pk).exam_set_id
            super().save_model(request, obj, form, change)
            examsets.assign(obj, new_set, request.user, request)
            obj.refresh_from_db()
            return
        if not change and obj.exam_set_id:
            new_set, obj.exam_set = obj.exam_set, None  # save first, then assign (audited)
            super().save_model(request, obj, form, change)
            examsets.assign(obj, new_set, request.user, request)
            return
        super().save_model(request, obj, form, change)


@admin.register(Enrolment)
class EnrolmentAdmin(ModelAdmin):
    list_display = ("user", "batch", "joined_at")
    list_filter = ("batch",)
    search_fields = ("user__email",)
    raw_id_fields = ("user",)
