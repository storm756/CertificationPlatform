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
    )
    list_filter = ("accepting", "status", "is_open_pool")
    search_fields = ("code", "name", "centre")
    inlines = [BatchMentorInline]


@admin.register(Enrolment)
class EnrolmentAdmin(ModelAdmin):
    list_display = ("user", "batch", "joined_at")
    list_filter = ("batch",)
    search_fields = ("user__email",)
    raw_id_fields = ("user",)
