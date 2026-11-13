from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

from apps.accounts import views as account_views
from apps.core.views import (
    grievance_view,
    healthz,
    help_view,
    home,
    people_photo,
    set_language,
    styleguide,
    terms_view,
)

urlpatterns = [
    path("healthz/", healthz, name="healthz"),
    path("styleguide/", styleguide, name="styleguide"),
    path("i18n/setlang/", set_language, name="set_language"),
    # Staff sign in through allauth so that TOTP is always applied.
    path("admin/login/", RedirectView.as_view(pattern_name="account_login", query_string=True)),
    path("admin/", admin.site.urls),
    path("rosetta/", include("rosetta.urls")),  # staff translators only (rules.can_use_rosetta)
    # Public sign-up is closed (D9); the only way in is /register.
    path("accounts/signup/", RedirectView.as_view(pattern_name="register")),
    path("accounts/", include("allauth.urls")),
    path("register/", account_views.register_view, name="register"),
    path("guardian/<str:token>/", account_views.guardian_consent_view, name="guardian_consent"),
    path("waiting/", account_views.waiting_for_guardian, name="waiting_for_guardian"),
    path("waiting/resend/", account_views.resend_guardian, name="resend_guardian"),
    path("reset/<str:token>/", account_views.mentor_reset_view, name="mentor_reset"),
    path("notice/dismiss/", account_views.dismiss_reset_notice, name="dismiss_reset_notice"),
    path("privacy/", account_views.privacy_view, name="privacy"),
    path("terms/", terms_view, name="terms"),
    path("grievance/", grievance_view, name="grievance"),
    path("help/", help_view, name="help"),
    path("people/<slug:slug>/", people_photo, name="people_photo"),
    path("start/", account_views.start, name="start"),
    path("mentor/", include("apps.mentors.urls")),
    path("learn/", include("apps.content.urls")),
    path("staff/", include("apps.staff.urls")),
    path("", include("apps.certificates.urls")),
    path("", include("apps.assessments.urls")),
    path("", home, name="home"),
]

handler404 = "apps.core.views.not_found"
handler500 = "apps.core.views.server_error"
