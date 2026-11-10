from django.contrib import admin, messages
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
    )
    list_filter = ("accepting", "status", "is_open_pool")
    search_fields = ("code", "name", "centre")
    inlines = [BatchMentorInline]
    actions = ["open_registration", "close_registration"]

    def _set_accepting(self, request, queryset, value):
        from apps.audit.services import audit

        done = 0
        for batch in queryset:
            if batch.accepting != value:
                batch.accepting = value
                batch.save(update_fields=["accepting", "updated_at"])
                audit("batch.registration_updated", actor=request.user, target=batch, request=request, was_accepting=not value, accepting=value, via="admin")  # fmt: skip
                done += 1
        self.message_user(request, f"{done} batch(es) updated.", messages.SUCCESS)

    @admin.action(description="Open registration for the selected batches")
    def open_registration(self, request, queryset):
        self._set_accepting(request, queryset, True)

    @admin.action(description="Close registration for the selected batches")
    def close_registration(self, request, queryset):
        self._set_accepting(request, queryset, False)


@admin.register(Enrolment)
class EnrolmentAdmin(ModelAdmin):
    list_display = ("user", "batch", "joined_at")
    list_filter = ("batch",)
    search_fields = ("user__email",)
    raw_id_fields = ("user",)
