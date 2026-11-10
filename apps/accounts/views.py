from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import SetPasswordForm
from django.contrib.sessions.models import Session
from django.db import transaction
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from django_ratelimit.decorators import ratelimit

from apps.audit.services import audit
from apps.batches.rules import accepting_batches

from . import guardian
from .forms import GuardianConfirmForm, RegistrationForm
from .models import MentorResetLink, Profile, Role, UserStatus
from .services import Outcome, register
from .tokens import hash_token


def _rate_key(group, request):
    # Per batch, not per IP: a classroom shares one Wi-Fi address (architecture 7.2).
    return request.POST.get("batch", "none")


@ratelimit(key=_rate_key, rate=settings.REGISTER_RATE, method="POST", block=False)
def register_view(request):
    now = timezone.now()
    if request.user.is_authenticated:
        return redirect("start")
    if not accepting_batches(now):
        # Nothing is open: no form, and a direct POST is refused the same way.
        return render(
            request, "registration/closed.html", status=200 if request.method == "GET" else 403
        )

    if request.method == "POST":
        if getattr(request, "limited", False):
            return render(request, "registration/too_many.html", status=429)
        form = RegistrationForm(request.POST, now=now)
        if form.is_valid():
            result = register(form.cleaned_data, request)
            if result.outcome == Outcome.BATCH_CLOSED:
                form.keep_posted_batch_choice()
                form.add_error(None, "Sorry, this batch is not accepting registrations.")
            elif result.outcome == Outcome.BUDGET_EXHAUSTED:
                form.keep_posted_batch_choice()
                form.add_error(None, "We are very busy today. Please try again tomorrow.")
            else:
                # CREATED and EXISTING_EMAIL look identical: no account fishing.
                return render(request, "registration/check_inbox.html")
    else:
        form = RegistrationForm(now=now)
    return render(request, "registration/register.html", {"form": form})


def guardian_consent_view(request, token):
    consent = guardian.find_by_token(token)
    if consent is None:
        return render(request, "registration/guardian_invalid.html", status=404)
    form = GuardianConfirmForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        if not guardian.confirm(consent, form.cleaned_data["guardian_name"], request):
            # replaced by a resend, expired, or already confirmed since the page was checked
            return render(request, "registration/guardian_invalid.html", status=404)
        return render(request, "registration/guardian_done.html")
    return render(
        request,
        "registration/guardian_confirm.html",
        {"consent": consent, "learner": consent.user.profile, "form": form},
    )


@login_required
def start(request):
    """Where everyone lands after signing in."""
    user = request.user
    if user.status == UserStatus.PENDING_GUARDIAN:
        return redirect("waiting_for_guardian")
    if user.role in (Role.MENTOR, Role.ADMIN):
        return redirect("mentor_home")
    from apps.assessments import programme
    from apps.results import views as results
    from apps.results.policy import compute_results

    profile = user.profile
    if (
        profile.pretest_prompted_at is None
        and programme.pretest_available()
        and not compute_results([user.pk])[user.pk].pretest_done
    ):
        # The pre-test is offered once, right after the first sign-in. "Later" returns here.
        profile.pretest_prompted_at = timezone.now()
        profile.save(update_fields=["pretest_prompted_at"])
        return redirect("programme_intro", kind="pretest")
    return results.dashboard(request)


@login_required
def waiting_for_guardian(request):
    user = request.user
    if user.status != UserStatus.PENDING_GUARDIAN:
        return redirect("start")
    return render(request, "accounts/waiting_for_guardian.html", {"consent": user.guardian_consent})


@login_required
@require_POST
@ratelimit(key="user", rate="5/h", method="POST", block=True)
def resend_guardian(request):
    if request.user.status == UserStatus.PENDING_GUARDIAN and guardian.resend(request.user):
        messages.success(request, "We have emailed your guardian again.")
    else:
        messages.error(request, "We could not send the email right now. Please try again later.")
    return redirect("waiting_for_guardian")


@login_required
@require_POST
def dismiss_reset_notice(request):
    Profile.objects.filter(user=request.user).update(mentor_reset_notice=False)
    return redirect(request.POST.get("next") or "start")


def _valid_reset_link(raw_token):
    link = (
        MentorResetLink.objects.select_related("user")
        .filter(token_hash=hash_token(raw_token), used_at__isnull=True)
        .first()
    )
    if link is None or link.expires_at < timezone.now() or not link.user.is_active:
        return None
    return link


@ratelimit(key="ip", rate="30/h", method="POST", block=True)
def mentor_reset_view(request, token):
    """A mentor-generated one-time link (architecture 7.4). Valid 1 hour, single use."""
    link = _valid_reset_link(token)
    if link is None:
        return render(request, "accounts/reset_link_invalid.html", status=404)
    form = SetPasswordForm(link.user, request.POST or None)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            link = (
                MentorResetLink.objects.select_for_update().select_related("user").get(pk=link.pk)
            )
            if link.used_at is not None:
                return render(request, "accounts/reset_link_invalid.html", status=404)
            form.save()
            link.used_at = timezone.now()
            link.save(update_fields=["used_at"])
            _end_all_sessions(link.user)
            Profile.objects.filter(user=link.user).update(
                mentor_reset_at=link.used_at, mentor_reset_notice=True
            )
            audit("password.mentor_reset_used", actor=link.user, target=link.user, request=request)
        messages.success(request, "Your password is changed. Please sign in.")
        return redirect("account_login")
    return render(request, "accounts/reset_link_form.html", {"form": form})


def _end_all_sessions(user) -> None:
    """Delete every server-side session that belongs to this user."""
    uid = str(user.pk)
    for session in Session.objects.filter(expire_date__gte=timezone.now()):
        if session.get_decoded().get("_auth_user_id") == uid:
            session.delete()


def privacy_view(request):
    return render(
        request, "registration/privacy.html", {"version": settings.PRIVACY_NOTICE_VERSION}
    )
