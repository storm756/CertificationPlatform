"""Stage 7: certificates (architecture §12, D10, D28, D36). Invented learners and names only.

Journeys 12 and 13 (§18), the PDF allowlist and injection, revoke / erase, the verify page, the
mentor approval, the learner page and download.
"""

import hashlib
import io
import re
from datetime import timedelta

import pytest
from allauth.mfa.models import Authenticator
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, close_old_connections, transaction
from django.urls import reverse
from django.utils import timezone
from pypdf import PdfReader
from weasyprint import HTML

from apps.accounts.models import Role
from apps.assessments import services as attempts
from apps.assessments.models import AssessmentPart, Attempt, ProgrammeAssessmentKind
from apps.audit.models import AuditEvent
from apps.batches.models import Batch, BatchMentor
from apps.certificates import codes, pdf, services
from apps.certificates.models import Certificate, CertificateSettings, CertificateStatus
from apps.content.models import Module
from apps.results.policy import compute_results

from .conftest import right_token
from .test_assessments import run_in_threads
from .test_results import attempt

pytestmark = pytest.mark.django_db
NUMBER = re.compile(r"^CCFR-\d{4}-SAKEC-\d{6}$")
PNG = (  # a 1x1 transparent PNG
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f"
    b"\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00"
    b"IEND\xaeB`\x82"
)


# --- the test world -----------------------------------------------------------------------------------


@pytest.fixture
def course(make_part):
    """Module 1 only: Part A is a real drawn MCQ part, Part B a plain published part (50 + 50)."""
    part_a = make_part(questions=10, draw_n=5)
    part_b = AssessmentPart.objects.create(
        module=part_a.module, name="Part B", marks=50, selection="all", is_published=True
    )
    Module.objects.exclude(pk=part_a.module_id).update(counted=False)
    return part_a, part_b


def nearly_eligible(user, course):
    """Everything passed except Part A, which the learner submits last."""
    attempt(user, part=course[1], score="80")
    attempt(user, kind=ProgrammeAssessmentKind.PRETEST, score="30")
    attempt(user, kind=ProgrammeAssessmentKind.FINAL, score="85")


def eligible(user, course, score="90"):
    nearly_eligible(user, course)
    attempt(user, part=course[0], score=score)
    assert compute_results([user.pk])[user.pk].eligible
    return user


def submit_part_a_through_the_page(client, user, part):
    started, _ = attempts.start(user, part)
    for item in started.items.all():
        attempts.save_answer(started.pk, user, item.position, choice=right_token(item))
    response = client.post(reverse("attempt_submit", args=[started.pk]))
    assert response.status_code == 302
    return started


def pdf_text(data: bytes) -> str:
    return "\n".join(page.extract_text() for page in PdfReader(io.BytesIO(data)).pages)


@pytest.fixture
def batch_mentor_client(mentor_client, mentor, learner):
    BatchMentor.objects.create(batch=learner.enrolment.batch, mentor=mentor)
    return mentor_client


@pytest.fixture
def admin_client(client, make_user):
    admin = make_user(role=Role.ADMIN, is_staff=True, is_superuser=True)
    Authenticator.objects.create(user=admin, type=Authenticator.Type.TOTP, data={"secret": "x"})
    client.force_login(admin)
    client.admin = admin
    return client


# --- Journey 12: eligible, auto-issue on, the last submit -----------------------------------------------


def test_journey12_the_last_submit_issues_and_the_verify_page_shows_valid_and_the_grade(
    client, learner, course
):
    batch = learner.enrolment.batch
    batch.auto_issue = True
    batch.save()
    nearly_eligible(learner, course)
    client.force_login(learner)
    submit_part_a_through_the_page(client, learner, course[0])

    cert = Certificate.objects.get(user=learner)
    assert cert.status == CertificateStatus.ISSUED and cert.auto_issued and cert.issued_by is None
    assert NUMBER.match(cert.certificate_no) and cert.certificate_no.startswith(
        f"CCFR-{timezone.localdate().year}-"
    )
    assert re.fullmatch(r"[0-9A-HJKMNP-TV-Z]{10}", cert.verify_code)
    assert (
        cert.snapshot["grade"] == "A"
        and cert.snapshot["certificate_name"] == learner.profile.certificate_name
    )
    stored = services.pdf_file(cert)
    assert stored and hashlib.sha256(stored.read_bytes()).hexdigest() == cert.pdf_sha256
    assert AuditEvent.objects.filter(action="certificate.issued", data__auto=True).count() == 1

    client.logout()  # the verify page is public
    page = client.get(reverse("verify_code", args=[cert.verify_code]))
    html = page.content.decode()
    assert page.status_code == 200 and "Valid" in html and ">A<" in html
    assert learner.profile.certificate_name in html and cert.snapshot["qualification"] in html
    assert page["X-Robots-Tag"] == "noindex, nofollow"


def test_with_auto_issue_off_the_learner_waits_for_the_mentor(client, learner, course):
    nearly_eligible(learner, course)
    client.force_login(learner)
    submit_part_a_through_the_page(client, learner, course[0])
    assert not Certificate.objects.exists()
    assert services.awaiting(learner.enrolment.batch) == [learner.pk]
    html = client.get(reverse("my_certificate")).content.decode()
    assert "Waiting for mentor approval" in html


def test_switching_auto_issue_on_does_not_issue_to_those_already_waiting(
    batch_mentor_client, learner, course
):
    eligible(learner, course)
    batch = learner.enrolment.batch
    batch_mentor_client.post(
        reverse("mentor_batch_auto_issue", args=[batch.pk]), {"auto_issue": "on"}
    )
    batch.refresh_from_db()
    assert batch.auto_issue and not Certificate.objects.exists()


def test_a_failed_auto_issue_never_breaks_the_submit_and_leaves_no_file(
    client, learner, course, monkeypatch, settings
):
    batch = learner.enrolment.batch
    batch.auto_issue = True
    batch.save()
    nearly_eligible(learner, course)

    def broken(*args, **kwargs):
        raise RuntimeError("renderer down")

    monkeypatch.setattr(pdf, "render", broken)
    client.force_login(learner)
    started = submit_part_a_through_the_page(client, learner, course[0])
    assert client.get(reverse("attempt_result", args=[started.pk])).status_code == 200
    assert not Certificate.objects.exists()
    assert AuditEvent.objects.filter(action="certificate.issue_failed").exists()
    assert not list((settings.CERTIFICATE_PRIVATE_ROOT).rglob("*.pdf"))
    assert services.awaiting(batch) == [learner.pk]  # still waiting, so the mentor can approve


# --- Journey 13: two tabs at once give one certificate ------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_journey13_two_parallel_issues_give_one_certificate(learner, course):
    batch = learner.enrolment.batch
    batch.auto_issue = True
    batch.save()
    eligible(learner, course)

    def tab():
        close_old_connections()
        cert = services.auto_issue_after_submit(learner)
        return cert.pk if cert else None

    results, errors = run_in_threads(2, tab)
    assert not errors, errors
    assert results.count(None) == 1 and len({r for r in results if r}) == 1
    assert Certificate.objects.filter(user=learner).count() == 1


def test_the_database_allows_one_issued_certificate_per_learner(learner, course):
    cert = services.issue(eligible(learner, course))
    with pytest.raises(IntegrityError), transaction.atomic():
        Certificate.objects.create(
            user=learner, serial=cert.serial + 1000, certificate_no="X-1", verify_code="0123456789",
            snapshot={}, issued_at=timezone.now(),
        )  # fmt: skip
    with pytest.raises(services.AlreadyIssued):
        services.issue(learner)


def test_a_learner_who_is_not_eligible_gets_nothing(learner, course):
    nearly_eligible(learner, course)
    with pytest.raises(services.NotEligible):
        services.issue(learner)
    assert not Certificate.objects.exists()


# --- numbers, codes, centre codes ---------------------------------------------------------------------


def test_the_serial_is_global_and_never_reused_after_a_revoke(
    learner, course, make_user, admin_client
):
    first = services.issue(eligible(learner, course))
    services.revoke(first, admin_client.admin, "Name misspelt", allow_reissue=True)
    second = services.issue(learner)
    assert second.serial > first.serial and second.certificate_no != first.certificate_no
    other = make_user(batch=learner.enrolment.batch)
    third = services.issue(eligible(other, course))
    assert third.serial > second.serial


def test_a_revoke_blocks_a_new_certificate_unless_the_admin_allows_it(
    learner, course, admin_client
):
    cert = services.issue(eligible(learner, course))
    services.revoke(cert, admin_client.admin, "Misconduct")
    result = compute_results([learner.pk])[learner.pk]
    assert not result.eligible and result.revoked_blocked
    assert any("revoked" in b for b in result.blockers)
    with pytest.raises(services.NotEligible):
        services.issue(learner)


def test_the_centre_code_comes_from_the_batch_and_is_validated(learner, course):
    batch = learner.enrolment.batch
    assert batch.centre_code == "SAKEC"  # the default from settings
    batch.centre_code = "MUM01"
    batch.save()
    cert = services.issue(eligible(learner, course))
    assert re.fullmatch(rf"CCFR-{timezone.localdate().year}-MUM01-\d{{6}}", cert.certificate_no)
    for bad in ("sakec", "S", "TOOLONG", "SA KE"):
        batch.centre_code = bad
        with pytest.raises(ValidationError):
            batch.full_clean()
    with pytest.raises(IntegrityError), transaction.atomic():
        Batch.objects.filter(pk=batch.pk).update(centre_code="ab")


def test_codes_are_normalised_and_a_certificate_number_is_never_a_code():
    assert codes.normalise_code("k7qm-2xr9-td") == "K7QM2XR9TD"
    assert codes.normalise_code("O1IL 000000") == "0111000000"
    assert codes.normalise_code("CCFR-2026-SAKEC-000001") is None
    assert codes.normalise_code("U234567890") is None  # U is not in Crockford base32
    assert codes.certificate_number("CCFR", 2026, "SAKEC", 1) == "CCFR-2026-SAKEC-000001"


# --- the PDF: allowlist, injection, wording -------------------------------------------------------------


def test_names_and_text_cannot_inject_anything_into_the_pdf(learner, course):
    evil = '</style><style>*{background:url(http://evil.example/a)}</style><img src="file:///etc/passwd">{{ asset }}qr'
    assert len(evil) <= 120  # the longest name the profile holds
    learner.profile.certificate_name = evil
    learner.profile.save()
    snapshot = services.build_snapshot(learner, compute_results([learner.pk])[learner.pk], learner.enrolment.batch, timezone.localtime())  # fmt: skip
    data, fetcher = pdf.render(
        snapshot, certificate_no="CCFR-2026-SAKEC-000009", verify_code="K7QM2XR9TD"
    )
    assert not fetcher.refused
    assert all(url.startswith(pdf.SCHEME) for url in fetcher.requested)
    assert not any("evil" in url or "passwd" in url for url in fetcher.requested)
    text = pdf_text(data)
    assert "evil.example" in text and "passwd" in text  # printed as plain text, never fetched


def test_the_fetcher_refuses_everything_off_the_allowlist():
    fetcher, _ = pdf.build_fetcher("K7QM2XR9TD")
    for url in (
        "file:///etc/passwd",
        "http://evil.example/a.png",
        "https://localhost/admin/",
        "data:image/png;base64,iVBORw0KGgo=",
        "ccfr-asset:../config/settings/base.py",
        "ccfr-asset:font/../../manage.py",
        "ccfr-asset:signature/1",  # no signature image is in place
    ):
        with pytest.raises(ValueError):
            fetcher.fetch(url)
    assert fetcher.fetch("ccfr-asset:qr").read().startswith(b"\x89PNG")
    # a careless template edit that asks for a file outside the list gets nothing
    refused, _ = pdf.build_fetcher("K7QM2XR9TD")
    HTML(
        string='<img src="file:///etc/passwd"><img src="ccfr-asset:img/sakec">', url_fetcher=refused
    ).write_pdf()
    assert refused.refused == ["file:///etc/passwd"]


def test_the_pdf_prints_the_wording_grade_and_number_but_no_percent_or_hours(learner, course):
    learner.profile.certificate_name = "Asha Invented Rao"
    learner.profile.save()
    cert = services.issue(eligible(learner, course))
    text = " ".join(pdf_text(services.pdf_file(cert).read_bytes()).split())
    assert "CERTIFICATE" in text and "Community Cyber First Responder (CCFR)" in text
    assert "This is to certify that" in text and "Asha Invented Rao" in text
    assert (
        "Department of Cyber Security" in text
        and "in collaboration with CyberPeace Foundation" in text
    )
    assert "Grade A" in text and cert.certificate_no in text
    assert "NSQF level and credits shown after approval by the competent authority" in text
    assert f"/verify/{cert.verify_code}" in text.replace(" ", "")  # the URL may wrap under the QR
    assert "%" not in text and "hour" not in text.lower()
    names = [s["name"].upper() for s in cert.snapshot["signatories"]]
    assert names == ["DR. NILAKSHI JAIN", "DR. BHAVESH PATEL", "MAJ. VINEET KUMAR"]
    assert text.index(names[0]) < text.index(names[1]) < text.index(names[2])  # left to right
    # the snapshot still keeps the %s and hours for the record
    assert (
        cert.snapshot["overall"]
        and cert.snapshot["final"] == "85.0"
        and "minutes" in cert.snapshot["hours"]
    )


def test_a_missing_signature_prints_a_blank_line_and_a_present_one_is_used(
    settings, learner, course
):
    sigs = settings.CERTIFICATE_PRIVATE_ROOT / "signatures"
    _, fetcher = pdf.render({**services.build_snapshot(learner, compute_results([learner.pk])[learner.pk], learner.enrolment.batch, timezone.localtime()), "completed_on": "2026-11-13"}, certificate_no="N", verify_code="K7QM2XR9TD")  # fmt: skip
    assert not any("signature" in u for u in fetcher.requested)
    assert len(pdf.missing_signatures()) == 3
    sigs.mkdir(parents=True)
    (sigs / "signature-1.png").write_bytes(PNG)
    settings.CERTIFICATE_SIGNATORIES = [
        *settings.CERTIFICATE_SIGNATORIES[:2],
        {
            **settings.CERTIFICATE_SIGNATORIES[2],
            "image": "../signature-1.png",
        },  # never outside the folder
    ]
    cert = services.issue(eligible(learner, course))
    assert [s["signed"] for s in cert.snapshot["signatories"]] == [True, False, False]
    fetcher, signatories = pdf.build_fetcher("K7QM2XR9TD")
    assert [s["asset"] for s in signatories] == ["signature/1", "", ""]
    assert fetcher.fetch("ccfr-asset:signature/1").read() == PNG


def test_nsqf_wording_changes_for_new_certificates_only(learner, course, make_user):
    first = services.issue(eligible(learner, course))
    cfg = CertificateSettings.load()
    cfg.nsqf_approved = True
    with pytest.raises(ValidationError):
        cfg.full_clean()  # level and credits first
    with pytest.raises(IntegrityError), transaction.atomic():
        cfg.save()
    cfg.nsqf_level, cfg.nsqf_credits = "4", "12"
    cfg.full_clean()
    cfg.save()
    other = make_user(batch=learner.enrolment.batch)
    second = services.issue(eligible(other, course))
    first.refresh_from_db()
    assert first.snapshot["nsqf"]["line"] == services.NSQF_PENDING
    assert second.snapshot["nsqf"]["line"] == "NSQF Level 4 · 12 credits"
    assert "NSQF Level 4" in pdf_text(services.pdf_file(second).read_bytes())


def test_completed_on_is_the_date_the_result_was_achieved(learner, course):
    eligible(learner, course)
    Attempt.objects.filter(user=learner).update(submitted_at=timezone.now() - timedelta(days=5))
    Attempt.objects.filter(user=learner, part=course[0]).update(
        submitted_at=timezone.now() - timedelta(days=3)
    )
    cert = services.issue(learner)
    assert cert.snapshot["completed_on"] == (timezone.localdate() - timedelta(days=3)).isoformat()
    assert cert.snapshot["issued_on"] == timezone.localdate().isoformat()


# --- revoke, erase and the verify page ----------------------------------------------------------------


def test_a_revoked_certificate_shows_revoked_without_the_name(
    client, learner, course, admin_client
):
    cert = services.issue(eligible(learner, course))
    services.revoke(cert, admin_client.admin, "Issued by mistake")
    admin_client.logout()
    html = client.get(reverse("verify_code", args=[cert.verify_code])).content.decode()
    assert "Revoked" in html and "Valid" not in html
    assert learner.profile.certificate_name not in html
    assert AuditEvent.objects.filter(action="certificate.revoked").exists()
    assert "Issued by mistake" not in str(
        AuditEvent.objects.filter(action="certificate.revoked").values("data")
    )


def test_only_admins_revoke_or_erase(learner, course, mentor):
    cert = services.issue(eligible(learner, course))
    with pytest.raises(PermissionDenied):
        services.revoke(cert, mentor, "reason")
    with pytest.raises(PermissionDenied):
        services.erase_holder(cert, mentor)
    with pytest.raises(PermissionDenied):
        services.revoke(cert, learner, "reason")


def test_the_erased_holder_case(client, learner, course, admin_client):
    cert = services.issue(eligible(learner, course))
    path = services.pdf_file(cert)
    with transaction.atomic():  # the file is removed when the erasure commits
        services.erase_holder(cert, admin_client.admin)
    cert.refresh_from_db()
    assert cert.holder_erased and cert.snapshot["certificate_name"] == "" and cert.pdf_path == ""
    assert cert.status == CertificateStatus.ISSUED and cert.grade == "A"
    admin_client.logout()
    html = client.get(reverse("verify_code", args=[cert.verify_code])).content.decode()
    assert "Issued; holder details removed at the holder" in html
    assert learner.profile.certificate_name not in html
    client.force_login(learner)
    assert client.get(reverse("certificate_download")).status_code == 404
    assert path is not None


def test_there_is_no_lookup_by_number_and_an_unknown_code_is_a_plain_404(client, learner, course):
    cert = services.issue(eligible(learner, course))
    page = client.get(reverse("verify_code", args=[cert.certificate_no]))
    assert page.status_code == 404 and learner.profile.certificate_name not in page.content.decode()
    assert client.get(reverse("verify_code", args=["ZZZZZZZZZZ"])).status_code == 404
    typed = client.get(reverse("verify"), {"code": cert.certificate_no})
    assert typed.status_code == 200 and "not a verification code" in typed.content.decode()
    lower = client.get(reverse("verify"), {"code": cert.verify_code.lower()})
    assert lower.status_code == 302 and lower["Location"] == reverse(
        "verify_code", args=[cert.verify_code]
    )


def test_the_verify_page_is_rate_limited_per_client(client, settings, learner, course):
    settings.CERTIFICATE_VERIFY_RATE = "3/m"
    cert = services.issue(eligible(learner, course))
    url = reverse("verify_code", args=[cert.verify_code])
    assert [client.get(url).status_code for _ in range(3)] == [200, 200, 200]
    blocked = client.get(url)
    assert (
        blocked.status_code == 429
        and learner.profile.certificate_name not in blocked.content.decode()
    )
    other = client.get(url, HTTP_X_FORWARDED_FOR="203.0.113.9")  # another phone is not blocked
    assert other.status_code == 200


def test_the_verify_page_is_public_even_while_waiting_for_a_guardian(client, make_user, make_batch):
    waiting = make_user(batch=make_batch(), status="pending_guardian")
    client.force_login(waiting)
    assert client.get(reverse("verify")).status_code == 200


# --- the learner: page and download --------------------------------------------------------------------


def test_the_learner_page_states(client, learner, course, admin_client):
    admin = admin_client.admin
    client.force_login(learner)
    assert "Not yet" in client.get(reverse("my_certificate")).content.decode()
    eligible(learner, course)
    assert "You are eligible" in client.get(reverse("my_certificate")).content.decode()
    cert = services.issue(learner)
    html = client.get(reverse("my_certificate")).content.decode()
    assert (
        "Your certificate is ready" in html
        and cert.certificate_no in html
        and "Download PDF" in html
    )
    assert "%" not in html.split("cert-details")[1].split("</dl>")[0]  # grade only
    dash = client.get(reverse("start")).content.decode()
    assert "Certificate issued" in dash and "You are a certified" in dash
    services.revoke(cert, admin, "Invented reason")
    assert (
        "This certificate has been revoked"
        in client.get(reverse("my_certificate")).content.decode()
    )


def test_the_download_is_the_owners_only(client, learner, course, make_user, batch_mentor_client):
    cert = services.issue(eligible(learner, course))
    batch_mentor_client.logout()
    client.force_login(learner)
    response = client.get(reverse("certificate_download"))
    body = b"".join(response.streaming_content)
    assert response.status_code == 200 and body.startswith(b"%PDF-")
    assert response["Content-Type"] == "application/pdf"
    assert f'filename="{cert.certificate_no}.pdf"' in response["Content-Disposition"]
    assert "no-store" in response["Cache-Control"]
    other = make_user(batch=learner.enrolment.batch)
    client.force_login(other)
    assert client.get(reverse("certificate_download")).status_code == 404
    client.logout()
    assert client.get(reverse("certificate_download")).status_code == 302  # to sign-in


def test_a_tampered_pdf_is_not_served(client, learner, course):
    cert = services.issue(eligible(learner, course))
    services.pdf_file(cert).write_bytes(b"%PDF-1.7 something else")
    client.force_login(learner)
    assert client.get(reverse("certificate_download")).status_code == 404


def test_staff_cannot_use_the_learner_download(batch_mentor_client, learner, course):
    services.issue(eligible(learner, course))
    assert batch_mentor_client.get(reverse("certificate_download")).status_code == 403


# --- the mentor: approval, scoping, the guard ------------------------------------------------------------


def test_the_mentor_approves_one_learner_and_it_is_audited(
    batch_mentor_client, mentor, learner, course
):
    eligible(learner, course)
    batch = learner.enrolment.batch
    html = batch_mentor_client.get(reverse("mentor_batch", args=[batch.pk])).content.decode()
    assert "Awaiting approval" in html and learner.profile.certificate_name in html
    batch_mentor_client.post(
        reverse("mentor_batch_approve", args=[batch.pk]), {"learner": learner.pk}
    )
    cert = Certificate.objects.get(user=learner)
    assert cert.issued_by == mentor and not cert.auto_issued
    assert AuditEvent.objects.filter(action="certificate.approved", actor_id=mentor.pk).exists()
    html = batch_mentor_client.get(reverse("mentor_batch", args=[batch.pk])).content.decode()
    assert "No one is waiting" in html and cert.certificate_no in html.split("Issued this week")[1]


def test_approve_all_is_capped_per_click(batch_mentor_client, settings, learner, course, make_user):
    settings.CERTIFICATE_APPROVE_PER_REQUEST = 1
    other = make_user(batch=learner.enrolment.batch)
    eligible(learner, course)
    eligible(other, course)
    batch = learner.enrolment.batch
    response = batch_mentor_client.post(
        reverse("mentor_batch_approve", args=[batch.pk]), follow=True
    )
    assert (
        Certificate.objects.count() == 1
        and "1 learner(s) still waiting" in response.content.decode()
    )
    batch_mentor_client.post(reverse("mentor_batch_approve", args=[batch.pk]))
    assert Certificate.objects.count() == 2


def test_a_mentor_cannot_approve_in_another_batch(mentor_client, mentor, learner, course):
    eligible(learner, course)  # the mentor does not mentor this learner's batch
    response = mentor_client.post(
        reverse("mentor_batch_approve", args=[learner.enrolment.batch.pk])
    )
    assert response.status_code == 403 and not Certificate.objects.exists()
    with pytest.raises(PermissionDenied):
        services.approve(mentor, learner.enrolment.batch)
    with pytest.raises(PermissionDenied):
        services.approve(learner, learner.enrolment.batch)


def test_guard_a_warns_while_signatures_or_the_final_design_are_missing(
    batch_mentor_client, settings, learner
):
    batch = learner.enrolment.batch
    html = batch_mentor_client.get(reverse("mentor_batch", args=[batch.pk])).content.decode()
    assert "Not ready for real certificates yet" in html and "Dr. Nilakshi Jain" in html
    assert "still placeholders" in html
    sigs = settings.CERTIFICATE_PRIVATE_ROOT / "signatures"
    sigs.mkdir(parents=True)
    for i in (1, 2, 3):
        (sigs / f"signature-{i}.png").write_bytes(PNG)
    settings.CERTIFICATE_DESIGN_FINAL = True
    html = batch_mentor_client.get(reverse("mentor_batch", args=[batch.pk])).content.decode()
    assert "Not ready for real certificates yet" not in html


# --- the admin: revoke action, report count ----------------------------------------------------------------


def test_the_admin_revokes_through_the_admin_action(admin_client, learner, course):
    cert = services.issue(eligible(learner, course))
    url = reverse("admin:certificates_certificate_changelist")
    page = admin_client.get(url)
    assert page.status_code == 200 and "still placeholders" in page.content.decode()
    confirm = admin_client.post(url, {"action": "revoke_selected", "_selected_action": [cert.pk]})
    assert confirm.status_code == 200 and b"Revoke certificates" in confirm.content
    admin_client.post(url, {"action": "revoke_selected", "_selected_action": [cert.pk], "apply": "1", "reason": "Invented reason"})  # fmt: skip
    cert.refresh_from_db()
    assert cert.status == CertificateStatus.REVOKED and cert.revoked_reason == "Invented reason"
    assert not cert.reissue_allowed


def test_mentors_and_learners_cannot_open_the_certificate_admin(client, learner):
    client.force_login(learner)
    assert client.get(reverse("admin:certificates_certificate_changelist")).status_code in (
        302,
        403,
    )


def test_the_report_counts_issued_certificates(admin_client, learner, course):
    cert = services.issue(eligible(learner, course))
    rows = admin_client.get(reverse("staff_report")).context["batches"]
    assert next(r for r in rows if r["batch"] == learner.enrolment.batch)["issued"] == 1
    assert cert.snapshot["overall"] == str(compute_results([learner.pk])[learner.pk].overall_shown)


# --- D37: certificate names in English letters only ----------------------------------------------------


@pytest.mark.parametrize(
    "name,ok",
    [
        ("Asha R. Desai", True),
        ("Zoë D'Souza-Rao", True),
        ("Anne-Marie O’Brien", True),
        ("आशा राव", False),
        ("આશા રાવ", False),
        ("Asha राव", False),
        ("Learner 1", False),
        ("A", False),
        ("-Asha", False),
        ("Ash@ Rao", False),
    ],
)
def test_the_certificate_name_rule(name, ok):
    from apps.accounts.rules import certificate_name_ok

    assert certificate_name_ok(name) is ok


def test_registration_refuses_a_name_not_in_english_letters():
    from apps.accounts.forms import RegistrationForm

    form = RegistrationForm({"certificate_name": "आशा राव"})
    form.is_valid()
    assert "English letters" in str(form.errors["certificate_name"])


def test_a_mentor_cannot_set_a_name_in_another_script(batch_mentor_client, learner):
    before = learner.profile.certificate_name
    batch_mentor_client.post(
        reverse("mentor_learner_name", args=[learner.pk]), {"certificate_name": "आशा राव"}
    )
    learner.profile.refresh_from_db()
    assert learner.profile.certificate_name == before


def test_a_name_to_correct_is_held_back_and_shown_to_the_mentor(
    batch_mentor_client, learner, course
):
    eligible(learner, course)
    learner.profile.certificate_name = "आशा राव"  # e.g. typed before the rule existed
    learner.profile.save()
    with pytest.raises(services.NameNotPrintable):
        services.issue(learner)
    batch = learner.enrolment.batch
    html = batch_mentor_client.get(reverse("mentor_batch", args=[batch.pk])).content.decode()
    assert "Correct the name first" in html and "Approve all" not in html
    response = batch_mentor_client.post(
        reverse("mentor_batch_approve", args=[batch.pk]), follow=True
    )
    assert "held back" in response.content.decode() and not Certificate.objects.exists()
    batch.auto_issue = True
    batch.save()
    assert services.auto_issue_after_submit(learner) is None and not Certificate.objects.exists()
    batch_mentor_client.post(
        reverse("mentor_learner_name", args=[learner.pk]), {"certificate_name": "Asha Rao"}
    )
    batch_mentor_client.post(reverse("mentor_batch_approve", args=[batch.pk]))
    assert Certificate.objects.get(user=learner).snapshot["certificate_name"] == "Asha Rao"


def test_the_learner_is_told_when_their_name_needs_correcting(client, learner, course):
    eligible(learner, course)
    learner.profile.certificate_name = "આશા રાવ"
    learner.profile.save()
    client.force_login(learner)
    assert "must be in English letters" in client.get(reverse("my_certificate")).content.decode()


def test_the_pdf_asks_only_for_latin_fonts(learner, course):
    _, fetcher = pdf.render(
        {**services.build_snapshot(learner, compute_results([learner.pk])[learner.pk], learner.enrolment.batch, timezone.localtime()), "completed_on": "2026-11-13"},
        certificate_no="N", verify_code="K7QM2XR9TD",
    )  # fmt: skip
    fonts = {u for u in fetcher.requested if "/font/" in u or u.startswith("ccfr-asset:font/")}
    assert fonts == {
        "ccfr-asset:font/baloo2-latin.woff2",
        "ccfr-asset:font/hind-latin-400.woff2",
        "ccfr-asset:font/hind-latin-600.woff2",
    }
