from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.forms import AdminPasswordChangeForm
from unfold.admin import ModelAdmin
from unfold.forms import UserChangeForm, UserCreationForm

from .models import User


class EmailUserCreationForm(UserCreationForm):
    class Meta:
        model = User
        fields = ("email",)


class EmailUserChangeForm(UserChangeForm):
    class Meta:
        model = User
        fields = "__all__"


@admin.register(User)
class UserAdmin(DjangoUserAdmin, ModelAdmin):
    form = EmailUserChangeForm
    add_form = EmailUserCreationForm
    change_password_form = AdminPasswordChangeForm
    ordering = ("email",)
    list_display = ("email", "role", "status", "is_staff", "is_active", "created_at")
    list_filter = ("role", "status", "is_staff", "is_active")
    search_fields = ("email",)
    readonly_fields = ("last_login", "created_at", "updated_at")
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Role", {"fields": ("role", "status")}),
        (
            "Permissions",
            {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")},
        ),
        ("Dates", {"fields": ("last_login", "created_at", "updated_at")}),
    )
    add_fieldsets = (
        (None, {"classes": ("wide",), "fields": ("email", "password1", "password2", "role")}),
    )
