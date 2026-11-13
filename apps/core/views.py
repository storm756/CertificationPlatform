from django import forms
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import connection
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST
from django.views.i18n import set_language as django_set_language

from . import people
from .faq import FAQ


PUBLIC_CACHE = "public, max-age=300"


def home(request):
    """The public landing page (Stage 9). Lessons need sign-in (D34), so its calls to action go to
    registration and sign-in. The module list is the live course, or a short note when none is loaded."""
    from apps.content.models import Module
    from apps.translations import pages as tpages


    modules = list(Module.objects.all())
    if modules:
        lookup = tpages.learning_lookup(modules)
        for module in modules:
            tpages.localise_module(module, lookup)
    return render(
        request,
        "landing.html",
        {
            "modules": modules,
            "faq": [(q, a) for q, a, on_landing in FAQ if on_landing],
            "people": people.people_to_show(),
            "signed_in": request.user.is_authenticated,
        },
    )


def help_view(request):
    return render(request, "public/help.html", {"faq": [(q, a) for q, a, _l in FAQ]})


def grievance_view(request):
    return render(request, "public/grievance.html")


def terms_view(request):
    return render(request, "public/terms.html")


def people_photo(request, slug):
    """A leader's photo, only while consent is on and the file is in PEOPLE_PHOTO_DIR (never in git)."""
    path = people.photo_path(slug) if settings.PEOPLE_CONSENT_GIVEN else None
    if path is None:
        raise Http404
    response = FileResponse(path.open("rb"), content_type=people.CONTENT_TYPES[path.suffix])
    response["Cache-Control"] = PUBLIC_CACHE
    return response


def not_found(request, exception=None):
    return render(request, "404.html", status=404)


def server_error(request):
    return render(request, "500.html", status=500)


def healthz(request):
    """Liveness + database check for Docker and the uptime pinger."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except Exception:
        return HttpResponse("db unavailable", status=503, content_type="text/plain")
    return HttpResponse("ok", content_type="text/plain")


@require_POST
def set_language(request):
    """Django's set_language (cookie for guests) plus Profile.preferred_language when signed in."""
    response = django_set_language(request)
    code = request.POST.get("language", "")
    profile = getattr(request.user, "profile", None) if request.user.is_authenticated else None
    if profile and code in dict(settings.LANGUAGES) and profile.preferred_language != code:
        profile.preferred_language = code
        profile.save(update_fields=["preferred_language"])
    return response


class _StyleguideForm(forms.Form):
    """Demo form for /styleguide only: a normal field, a hint, an error, a password and more."""

    name = forms.CharField(label="Full name", help_text="As it should appear on your certificate.")
    email = forms.EmailField(label="Email address")
    password = forms.CharField(label="Password", widget=forms.PasswordInput)
    language = forms.ChoiceField(label="Language", choices=[("en", "English"), ("hi", "हिन्दी")])
    agree = forms.BooleanField(label="I agree to the terms")


@login_required
def styleguide(request):
    """Every shared component in every state, for the reviewer (Stage 1.5). Staff only."""
    if not request.user.is_staff:
        raise PermissionDenied
    broken = _StyleguideForm(
        {"name": "", "email": "not-an-email", "password": "", "language": "en", "agree": ""}
    )
    broken.full_clean()
    items = [
        {"number": n, "answered": n in (1, 2, 3, 6), "flagged": n in (3, 5), "current": n == 4}
        for n in range(1, 13)
    ]
    stages = [
        ("learn", "Learn", "book"),
        ("practise", "Practise", "code"),
        ("assess", "Assess", "shield"),
        ("certify", "Certify", "award"),
    ]
    return render(
        request,
        "styleguide.html",
        {
            "form": _StyleguideForm(),
            "broken": broken,
            "items": items,
            "stages": stages,
            "colours": [
                "navy",
                "teal",
                "teal-bright",
                "cyan",
                "mustard",
                "mustard-deep",
                "terracotta",
                "plum",
                "blue",
                "danger",
                "bg",
                "surface",
                "surface-3",
            ],  # fmt: skip
        },
    )
