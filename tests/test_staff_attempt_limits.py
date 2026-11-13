"""D32 in the staff tools: the admin-only attempt-limits page."""

import pytest
from allauth.mfa.models import Authenticator
from django.urls import reverse

from apps.accounts.models import Role
from apps.assessments.models import AssessmentPart, ProgrammeAssessment, ProgrammeAssessmentKind
from apps.audit.models import AuditEvent

from .test_results import make_parts

pytestmark = pytest.mark.django_db


@pytest.fixture
def limits_admin(client, make_user):
    admin = make_user(role=Role.ADMIN, is_staff=True, is_superuser=True)
    Authenticator.objects.create(user=admin, type=Authenticator.Type.TOTP, data={"secret": "x"})
    client.force_login(admin)
    return client


@pytest.fixture
def final():
    obj, _ = ProgrammeAssessment.objects.get_or_create(kind=ProgrammeAssessmentKind.FINAL)
    return obj


def _post(client, part, final, part_value, final_value):
    return client.post(
        reverse("staff_attempts"), {f"part_{part.pk}": part_value, f"final_{final.pk}": final_value}
    )


def _first_part():
    make_parts()
    return AssessmentPart.objects.order_by("pk").first()


def test_admin_sets_and_clears_limits_and_each_change_is_audited(limits_admin, final):
    part = _first_part()
    assert limits_admin.get(reverse("staff_attempts")).status_code == 200
    r = _post(limits_admin, part, final, "3", "2")
    assert r.status_code == 302
    part.refresh_from_db()
    final.refresh_from_db()
    assert (part.max_attempts, final.max_attempts) == (3, 2)
    events = AuditEvent.objects.filter(action="assessment.max_attempts_changed")
    assert events.count() == 2
    _post(limits_admin, part, final, "", "2")  # blank clears; the unchanged final adds no audit
    part.refresh_from_db()
    assert part.max_attempts is None
    assert events.count() == 3


@pytest.mark.parametrize("bad", ["0", "-1", "abc", "101", "1.5"])
def test_bad_values_save_nothing(limits_admin, final, bad):
    part = _first_part()
    r = _post(limits_admin, part, final, bad, "2")
    assert r.status_code == 200 and b"whole number" in r.content
    part.refresh_from_db()
    final.refresh_from_db()
    assert part.max_attempts is None and final.max_attempts is None


def test_mentor_and_learner_get_403_and_it_is_logged(mentor_client, mentor, final):
    part = _first_part()
    assert mentor_client.get(reverse("staff_attempts")).status_code == 403
    assert _post(mentor_client, part, final, "1", "1").status_code == 403
    part.refresh_from_db()
    assert part.max_attempts is None
    paths = AuditEvent.objects.filter(action="access.denied", actor_id=mentor.pk).values_list(
        "data__path", flat=True
    )
    assert "/staff/attempts/" in set(paths)
