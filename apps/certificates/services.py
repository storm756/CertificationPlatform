"""Issuing, approving, revoking and erasing certificates (architecture §12, D10, D28, D36).

Business rules live here. `issue()` is the only way a certificate is created: it locks the learner,
re-checks eligibility with `compute_results`, takes the next serial, snapshots the result, renders
the PDF and saves everything in one transaction. A learner can hold one issued certificate; the
row lock and a partial unique index both enforce it.
"""

import hashlib
import logging
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Role, User
from apps.audit.services import audit
from apps.batches.models import Batch, Enrolment
from apps.batches.scoping import batches_for
from apps.results import policy
from apps.results.policy import compute_results

from . import codes, pdf
from .models import Certificate, CertificateSettings, CertificateStatus

logger = logging.getLogger(__name__)

NSQF_PENDING = "NSQF level and credits shown after approval by the competent authority"
ISSUED_RECENTLY_DAYS = 7


class CertificateError(Exception):
    pass


class NotEligible(CertificateError):
    def __init__(self, reasons):
        super().__init__("Not eligible")
        self.reasons = reasons


class AlreadyIssued(CertificateError):
    def __init__(self, certificate):
        super().__init__("Already issued")
        self.certificate = certificate


def is_admin(user) -> bool:
    return bool(user and user.is_authenticated and (user.role == Role.ADMIN or user.is_superuser))


# --- what goes on the certificate ----------------------------------------------------------------


def nsqf_line(cfg: CertificateSettings) -> str:
    if cfg.nsqf_approved:
        return f"NSQF Level {cfg.nsqf_level} · {cfg.nsqf_credits} credits"
    return NSQF_PENDING


def build_snapshot(user, result, batch, issued_local) -> dict:
    """Everything the certificate states, fixed at issue (§12). The PDF prints the grade only; the
    percentages and hours are kept for the record and are never printed (D36)."""
    from apps.content.services import hours_for

    cfg = CertificateSettings.load()
    achieved = result.achieved_at
    completed = timezone.localtime(achieved).date() if achieved else issued_local.date()
    return {
        "certificate_name": user.profile.certificate_name,
        "qualification": settings.CERTIFICATE_QUALIFICATION,
        "programme": settings.PROGRAMME_NAME,
        "programme_short": settings.PROGRAMME_SHORT,
        "batch": {"id": batch.pk, "code": batch.code, "name": batch.name},
        "centre_code": batch.centre_code,
        "completed_on": completed.isoformat(),
        "issued_on": issued_local.date().isoformat(),
        "grade": result.grade,
        "overall": str(result.overall_shown),
        "modules_mean": str(result.modules_shown),
        "final": str(result.final_shown),
        "modules": [{"number": m.number, "percent": str(m.shown)} for m in result.modules],
        "hours": hours_for(user),
        "policy": {
            "weights": f"modules {policy.WEIGHT_MODULES} + final {policy.WEIGHT_FINAL}",
            "pass_mark": str(policy.PASS_MARK),
            "grades": ", ".join(f"{letter} ≥ {floor}" for floor, letter in policy.GRADES),
        },
        "nsqf": {
            "approved": cfg.nsqf_approved,
            "level": cfg.nsqf_level if cfg.nsqf_approved else "",
            "credits": cfg.nsqf_credits if cfg.nsqf_approved else "",
            "line": nsqf_line(cfg),
        },
        "signatories": [
            {
                "name": s["name"],
                "designation": s["designation"],
                "organisation": s.get("organisation", ""),
                "signed": pdf.signature_file(s) is not None,
            }
            for s in settings.CERTIFICATE_SIGNATORIES
        ],
        "design": "final" if settings.CERTIFICATE_DESIGN_FINAL else "placeholder",
    }


# --- files -------------------------------------------------------------------------------------


def private_root() -> Path:
    return Path(settings.CERTIFICATE_PRIVATE_ROOT)


def pdf_file(cert: Certificate) -> Path | None:
    """The stored PDF, or None. The stored path is ours, but it is still kept inside the root."""
    if not cert.pdf_path:
        return None
    root = (private_root() / "certificates").resolve()
    path = (private_root() / cert.pdf_path).resolve()
    if root not in path.parents or not path.is_file():
        return None
    return path


def _write_pdf(certificate_no: str, year: int, data: bytes) -> tuple[str, Path]:
    relative = f"certificates/{year}/{certificate_no}.pdf"
    path = private_root() / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:  # never overwrite: a number is used once
        handle.write(data)
    return relative, path


def _unused_code() -> str:
    for _ in range(5):
        code = codes.new_verify_code()
        if not Certificate.objects.filter(verify_code=code).exists():
            return code
    raise CertificateError("Could not find an unused verify code")  # pragma: no cover


# --- issue -------------------------------------------------------------------------------------


def issue(user, *, actor=None, auto=False, request=None, now=None) -> Certificate:
    """Issue the learner's certificate, or raise NotEligible / AlreadyIssued.

    The serial is taken inside the transaction; if anything fails after that, the serial is
    skipped (never reused) and the PDF written so far is deleted.
    """
    now = now or timezone.now()
    written = None
    try:
        with transaction.atomic():
            User.objects.select_for_update().get(pk=user.pk)
            existing = Certificate.objects.filter(user_id=user.pk, status=CertificateStatus.ISSUED).first()  # fmt: skip
            if existing:
                raise AlreadyIssued(existing)
            result = compute_results([user.pk])[user.pk]
            if not result.eligible:
                raise NotEligible(result.blockers)
            batch = Enrolment.objects.select_related("batch").get(user_id=user.pk).batch
            learner = User.objects.select_related("profile").get(pk=user.pk)
            local = timezone.localtime(now)
            serial = codes.next_serial()
            number = codes.certificate_number(settings.CERTIFICATE_PREFIX, local.year, batch.centre_code, serial)  # fmt: skip
            code = _unused_code()
            snapshot = build_snapshot(learner, result, batch, local)
            data, _ = pdf.render(snapshot, certificate_no=number, verify_code=code)
            relative, written = _write_pdf(number, local.year, data)
            cert = Certificate.objects.create(
                user_id=user.pk,
                serial=serial,
                certificate_no=number,
                verify_code=code,
                snapshot=snapshot,
                pdf_path=relative,
                pdf_sha256=hashlib.sha256(data).hexdigest(),
                issued_at=now,
                issued_by=actor,
                auto_issued=auto,
            )
            audit(
                "certificate.issued",
                actor=actor,
                target=cert,
                request=request,
                user=user.pk,
                batch=batch.pk,
                serial=serial,
                auto=auto,
            )
    except Exception:
        if written is not None:
            written.unlink(missing_ok=True)
        raise
    return cert


def auto_issue_after_submit(user, request=None) -> Certificate | None:
    """Called after a learner's own submit (§12). Issues only when their batch has auto-issue on
    and they are eligible now. A failure is logged and audited but never breaks the result page:
    the learner then waits in the mentor's "Awaiting approval" list."""
    if not Batch.objects.filter(enrolments__user_id=user.pk, auto_issue=True).exists():
        return None
    if not compute_results([user.pk])[user.pk].eligible:
        return None
    try:
        return issue(user, auto=True, request=request)
    except (NotEligible, AlreadyIssued):
        return None
    except Exception:
        logger.exception("certificate auto-issue failed for user %s", user.pk)
        audit("certificate.issue_failed", target=user, request=request, auto=True)
        return None


# --- the learner's view ------------------------------------------------------------------------


def current_certificate(user) -> Certificate | None:
    """The learner's issued certificate, else their latest revoked one, else None."""
    mine = Certificate.objects.filter(user=user)
    return mine.filter(status=CertificateStatus.ISSUED).first() or mine.first()


def certificate_state(cert, result) -> str:
    """unavailable / awaiting / issued / erased / revoked, as on the prototype's certificate page."""
    if cert and cert.is_issued:
        return "erased" if cert.holder_erased else "issued"
    if result.eligible:
        return "awaiting"  # includes a learner whose revoked certificate may be re-issued
    if cert:
        return "revoked"
    return "unavailable"


# --- mentor approval ---------------------------------------------------------------------------


def awaiting(batch) -> list[int]:
    """Learners of this batch who are eligible and hold no certificate, whatever the auto-issue
    switch says (so a learner an automatic step missed is never lost)."""
    ids = list(Enrolment.objects.filter(batch=batch).values_list("user_id", flat=True))
    results = compute_results(ids)
    return [uid for uid in ids if results[uid].eligible]


def approve(actor, batch, user_ids=None, request=None) -> dict:
    """Issue certificates to eligible learners of a batch the actor may manage (mentor or admin).

    `user_ids` limits it to some learners (one "Approve" button); None means "Approve all". At most
    CERTIFICATE_APPROVE_PER_REQUEST are issued per call so a request stays short; the rest wait.
    """
    if (
        actor.role not in (Role.MENTOR, Role.ADMIN)
        or not batches_for(actor).filter(pk=batch.pk).exists()
    ):
        raise PermissionDenied
    waiting = awaiting(batch)
    if user_ids is not None:
        wanted = {int(u) for u in user_ids}
        waiting = [uid for uid in waiting if uid in wanted]
    issued, failed = 0, 0
    for uid in waiting[: settings.CERTIFICATE_APPROVE_PER_REQUEST]:
        try:
            issue(User.objects.get(pk=uid), actor=actor, request=request)
            issued += 1
        except (NotEligible, AlreadyIssued):
            continue
        except Exception:
            logger.exception("certificate issue failed for user %s", uid)
            audit(
                "certificate.issue_failed", actor=actor, request=request, user=uid, batch=batch.pk
            )
            failed += 1
    audit("certificate.approved", actor=actor, target=batch, request=request, issued=issued, failed=failed, asked=len(waiting))  # fmt: skip
    return {"issued": issued, "failed": failed, "remaining": max(len(waiting) - issued, 0)}


def issued_recently(batch, now=None):
    now = now or timezone.now()
    return (
        Certificate.objects.filter(
            user__enrolment__batch=batch,
            status=CertificateStatus.ISSUED,
            issued_at__gte=now - timedelta(days=ISSUED_RECENTLY_DAYS),
        )
        .select_related("user__profile")
        .order_by("-issued_at")
    )


def issue_warnings() -> list[str]:
    """Guard A (D36): reasons not to approve real learners yet. Approving still works."""
    out = []
    missing = pdf.missing_signatures()
    if missing:
        out.append(
            "Signature images are missing for " + ", ".join(missing) + ". "
            "Their names will print over a blank signature line."
        )
    if not settings.CERTIFICATE_DESIGN_FINAL:
        out.append("The certificate design and the CCFR emblem are still placeholders.")
    return out


# --- revoke and erase (admin only) -------------------------------------------------------------


def revoke(cert, actor, reason: str, *, allow_reissue=False, request=None) -> Certificate:
    """Mark a certificate revoked. The verify page then says "Revoked". Admin only (§5)."""
    if not is_admin(actor):
        raise PermissionDenied
    reason = (reason or "").strip()
    if not reason:
        raise ValueError("Give a reason for revoking.")
    with transaction.atomic():
        cert = Certificate.objects.select_for_update().get(pk=cert.pk)
        if cert.status == CertificateStatus.REVOKED:
            return cert
        cert.status = CertificateStatus.REVOKED
        cert.revoked_at = timezone.now()
        cert.revoked_by = actor
        cert.revoked_reason = reason
        cert.reissue_allowed = bool(allow_reissue)
        cert.save(update_fields=["status", "revoked_at", "revoked_by", "revoked_reason", "reissue_allowed", "updated_at"])  # fmt: skip
        # the reason is kept on the certificate, not in the audit log (it may contain names)
        audit("certificate.revoked", actor=actor, target=cert, request=request, reissue_allowed=cert.reissue_allowed)  # fmt: skip
    return cert


def erase_holder(cert, actor, request=None) -> Certificate:
    """The holder asked for erasure (DPDP): blank the printed name and delete the PDF, keep the
    number, grade, dates and status, so the verify page can still answer for the paper copy."""
    if not is_admin(actor):
        raise PermissionDenied
    with transaction.atomic():
        cert = Certificate.objects.select_for_update().get(pk=cert.pk)
        if cert.holder_erased:
            return cert
        path = pdf_file(cert)
        cert.snapshot = {**cert.snapshot, "certificate_name": ""}
        cert.pdf_path = ""
        cert.holder_erased_at = timezone.now()
        cert.save(update_fields=["snapshot", "pdf_path", "holder_erased_at", "updated_at"])
        audit("certificate.holder_erased", actor=actor, target=cert, request=request)
        if path is not None:
            transaction.on_commit(lambda: path.unlink(missing_ok=True))
    return cert
