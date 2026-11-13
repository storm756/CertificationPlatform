from datetime import timedelta

from allauth.account.models import EmailAddress
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Exists, OuterRef
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.accounts.models import Role
from apps.audit.services import audit
from apps.batches import services
from apps.batches.models import Enrolment
from apps.batches.rules import is_accepting, seats_used
from apps.batches.scoping import batches_for
from apps.certificates import services as certificates

from . import dashboard, export
from .forms import CertificateNameForm, MoveLearnerForm, NewBatchForm, RegistrationSettingsForm

NEW_SIGNUP_DAYS = 7


def mentor_required(view):
    """Mentors and admins only. A learner who opens a mentor URL gets a 403 and a log line."""

    @login_required
    def wrapper(request, *args, **kwargs):
        if request.user.role not in (Role.MENTOR, Role.ADMIN):
            audit("access.denied", actor=request.user, request=request, path=request.path)
            raise PermissionDenied
        return view(request, *args, **kwargs)

    wrapper.__name__ = view.__name__
    return wrapper


@mentor_required
def home(request):
    now = timezone.now()
    rows = []
    for batch in batches_for(request.user).annotate(learners=Count("enrolments")):
        rows.append(
            {"batch": batch, "open": is_accepting(batch, now), "seats": seats_used(batch, now)}
        )
    return render(request, "mentors/home.html", {"rows": rows})


@mentor_required
def batch_new(request):
    form = NewBatchForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        batch = services.create_batch(request.user, form.cleaned_data, request)
        messages.success(
            request, f"Batch {batch.code} created. Registration is closed until you open it."
        )
        return redirect("mentor_batch", pk=batch.pk)
    return render(request, "mentors/batch_new.html", {"form": form})


def _roster(batch):
    verified = EmailAddress.objects.filter(user=OuterRef("user"), verified=True)
    return (
        Enrolment.objects.filter(batch=batch)
        .select_related("user", "user__profile")
        .annotate(email_verified=Exists(verified))
        .order_by("-joined_at")
    )


@mentor_required
def batch_detail(request, pk):
    batch = services.scoped_batch(request.user, pk, request)
    now = timezone.now()
    roster = list(_roster(batch))
    cutoff = now - timedelta(days=NEW_SIGNUP_DAYS)
    return render(
        request,
        "mentors/batch_detail.html",
        {
            "batch": batch,
            "overview": dashboard.batch_overview(batch, now),
            "roster": roster,
            "new_signups": [e for e in roster if e.joined_at >= cutoff],
            "accepting_now": is_accepting(batch, now),
            "seats": seats_used(batch, now),
            "form": RegistrationSettingsForm.for_batch(batch),
            "cert_warnings": certificates.issue_warnings(),
        },
    )


@mentor_required
@require_POST
def batch_settings(request, pk):
    batch = services.scoped_batch(request.user, pk, request)
    form = RegistrationSettingsForm(request.POST)
    if form.is_valid():
        services.update_registration(request.user, batch, form.cleaned_data, request)
        messages.success(request, "Registration settings saved.")
        return redirect("mentor_batch", pk=batch.pk)
    now = timezone.now()
    return render(
        request,
        "mentors/batch_detail.html",
        {
            "batch": batch,
            "roster": list(_roster(batch)),
            "new_signups": [],
            "overview": dashboard.batch_overview(batch, now),
            "accepting_now": is_accepting(batch, now),
            "seats": seats_used(batch, now),
            "form": form,
            "cert_warnings": certificates.issue_warnings(),
        },
        status=400,
    )


def _learner_context(request, enrolment, **extra):
    return {
        "enrolment": enrolment,
        "learner": enrolment.user,
        "move_form": MoveLearnerForm(mentor=request.user, current_batch=enrolment.batch),
        "name_form": CertificateNameForm(
            initial={"certificate_name": enrolment.user.profile.certificate_name}
        ),
        **extra,
    }


@mentor_required
def learner_detail(request, learner_id):
    enrolment = services.scoped_enrolment(request.user, learner_id, request)
    return render(request, "mentors/learner.html", _learner_context(request, enrolment))


@mentor_required
@require_POST
def learner_move(request, learner_id):
    enrolment = services.scoped_enrolment(request.user, learner_id, request)
    if not request.POST.get("batch", "").strip():
        # Nothing chosen is an honest mistake: show the form again with a message.
        form = MoveLearnerForm(request.POST, mentor=request.user, current_batch=enrolment.batch)
        form.is_valid()  # fills the translatable "Pick a batch." error
        return render(
            request,
            "mentors/learner.html",
            _learner_context(request, enrolment, move_form=form),
            status=400,
        )
    form = MoveLearnerForm(request.POST, mentor=request.user, current_batch=enrolment.batch)
    if form.is_valid():
        services.move_learner(request.user, enrolment, form.cleaned_data["batch"], request)
        messages.success(request, "Learner moved.")
        return redirect("mentor_learner", learner_id=learner_id)
    # Any other value is a batch that doesn't exist or isn't this mentor's. Both get the same
    # 403 and the response never says which.
    audit(
        "access.denied",
        actor=request.user,
        request=request,
        action_asked="move",
        target_id_asked=str(learner_id),
    )
    raise PermissionDenied


@mentor_required
@require_POST
def learner_name(request, learner_id):
    enrolment = services.scoped_enrolment(request.user, learner_id, request)
    form = CertificateNameForm(request.POST)
    if form.is_valid():
        services.change_certificate_name(
            request.user, enrolment.user, form.cleaned_data["certificate_name"], request
        )
        messages.success(request, "Certificate name changed.")
        return redirect("mentor_learner", learner_id=learner_id)
    enrolment.refresh_from_db()
    return render(
        request,
        "mentors/learner.html",
        _learner_context(request, enrolment, name_form=form),
        status=400,
    )


@mentor_required
@require_POST
def learner_reset_link(request, learner_id):
    enrolment = services.scoped_enrolment(request.user, learner_id, request)
    raw = services.issue_reset_link(request.user, enrolment.user, request)
    url = request.build_absolute_uri(reverse("mentor_reset", args=[raw]))
    # Shown once on this response. It is never stored or logged in clear.
    response = render(
        request,
        "mentors/reset_link.html",
        {"learner": enrolment.user, "url": url, "enrolment": enrolment},
    )
    response["Cache-Control"] = "no-store"
    return response


@mentor_required
@require_POST
def batch_auto_issue(request, pk):
    batch = services.scoped_batch(request.user, pk, request)
    services.set_auto_issue(request.user, batch, request.POST.get("auto_issue") == "on", request)
    messages.success(request, "Auto-issue updated.")
    return redirect("mentor_batch", pk=batch.pk)


@mentor_required
@require_POST
def batch_approve(request, pk):
    """Approve certificates (§12): one learner (`learner` in the form) or everyone waiting."""
    batch = services.scoped_batch(request.user, pk, request)
    learner = request.POST.get("learner", "").strip()
    ids = [learner] if learner.isdigit() else None
    outcome = certificates.approve(request.user, batch, ids, request)
    if outcome["issued"]:
        messages.success(request, f"{outcome['issued']} certificate(s) issued.")
    if outcome["held"]:
        messages.warning(
            request,
            f"{outcome['held']} learner(s) held back: their certificate name is not in English letters. Correct the name on the learner's page, then approve.",
        )
    if outcome["failed"]:
        messages.error(
            request,
            f"{outcome['failed']} certificate(s) could not be issued. They are still waiting; try again or tell an admin.",
        )
    elif outcome["remaining"] and ids is None:
        messages.info(
            request,
            f"{outcome['remaining']} learner(s) still waiting. Click Approve all again to continue.",
        )
    if not outcome["issued"] and not outcome["failed"] and not outcome["held"]:
        messages.info(request, "Nobody was waiting for approval.")
    return redirect(f"{reverse('mentor_batch', args=[batch.pk])}#certificates")


@mentor_required
@require_POST
def batch_export(request, pk):
    """The batch's results as a CSV download. Audited; every cell is spreadsheet-safe."""
    batch = services.scoped_batch(request.user, pk, request)
    overview = dashboard.batch_overview(batch)
    body = export.batch_csv(overview, batch)
    audit("batch.exported", actor=request.user, target=batch, request=request, rows=len(overview["rows"]))  # fmt: skip
    response = HttpResponse(body, content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{batch.code}-results.csv"'
    response["Cache-Control"] = "no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response
