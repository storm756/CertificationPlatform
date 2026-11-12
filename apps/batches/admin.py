from django import forms
from django.contrib import admin
from django.core.exceptions import ValidationError
from unfold.admin import ModelAdmin, TabularInline

from .models import Batch, BatchMentor, Enrolment


class BatchMentorInline(TabularInline):
    model = BatchMentor
    extra = 0
    autocomplete_fields = ["mentor"]


class BatchForm(forms.ModelForm):
    """Remembers which exam set the page was opened with, so a save can tell "the admin chose a
    different set" from "the admin edited something else on a stale page"."""

    exam_set_loaded = forms.CharField(required=False, widget=forms.HiddenInput)

    class Meta:
        model = Batch
        fields = "__all__"  # noqa: DJ007

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "exam_set" not in self.fields:  # mentors: the set is read-only, nothing to track
            del self.fields["exam_set_loaded"]
        elif self.instance.pk and not self.is_bound:
            self.initial["exam_set_loaded"] = self.instance.exam_set_id or ""

    def clean(self):
        data = super().clean()
        if "exam_set" in self.fields and self.instance.pk and "exam_set_loaded" in data:
            loaded = str(data.get("exam_set_loaded") or "")
            chosen = str(data["exam_set"].pk) if data.get("exam_set") else ""
            current = str(
                Batch.objects.values_list("exam_set_id", flat=True).get(pk=self.instance.pk) or ""
            )
            if chosen != loaded and current != loaded:
                raise ValidationError(
                    "Another admin changed this batch's exam set while you had the page open. "
                    "Reload the page and check the set before changing it."
                )
        return data


@admin.register(Batch)
class BatchAdmin(ModelAdmin):
    form = BatchForm
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
        """The exam set is never written by a plain save: an unrelated edit keeps whatever set the
        batch has now, even if another admin changed it while this page was open. A real change
        goes through examsets.assign, which is admin-only, checked and audited."""
        from apps.assessments import examsets

        if not change:
            wanted = obj.exam_set if obj.exam_set_id else None
            obj.exam_set = None  # save first, then assign (audited)
            super().save_model(request, obj, form, change)
            if wanted:
                examsets.assign(obj, wanted, request.user, request)
            return
        current = Batch.objects.select_for_update().get(pk=obj.pk)
        chosen = obj.exam_set if "exam_set" in form.fields else None
        loaded = None
        if "exam_set_loaded" in form.fields:
            loaded = str(form.cleaned_data.get("exam_set_loaded") or "")
        really_changed = (
            "exam_set" in form.fields and loaded is not None
            and str(chosen.pk if chosen else "") != loaded
        )  # fmt: skip
        obj.exam_set_id = current.exam_set_id  # keep the latest assignment
        super().save_model(request, obj, form, change)
        if really_changed:
            examsets.assign(obj, chosen, request.user, request)
        obj.refresh_from_db()


@admin.register(Enrolment)
class EnrolmentAdmin(ModelAdmin):
    list_display = ("user", "batch", "joined_at")
    list_filter = ("batch",)
    search_fields = ("user__email",)
    raw_id_fields = ("user",)
