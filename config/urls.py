from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

from apps.core.views import healthz, home

urlpatterns = [
    path("healthz/", healthz, name="healthz"),
    # Staff sign in through allauth so that TOTP is always applied.
    path("admin/login/", RedirectView.as_view(pattern_name="account_login", query_string=True)),
    path("admin/", admin.site.urls),
    path("accounts/", include("allauth.urls")),
    path("", home, name="home"),
]
