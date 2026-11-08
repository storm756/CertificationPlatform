from django.contrib import admin
from unfold.admin import ModelAdmin

from .models import AuditEvent


@admin.register(AuditEvent)
class AuditEventAdmin(ModelAdmin):
    list_display = ("at", "action", "actor_id", "target_type", "target_id")
    list_filter = ("action", "target_type")
    search_fields = ("action", "target_id", "actor_id")
    readonly_fields = [f.name for f in AuditEvent._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
