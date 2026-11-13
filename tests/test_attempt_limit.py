"""D32: the optional attempt limit on assessment parts and the final. Invented data only."""

import pytest
from django.contrib.admin.sites import AdminSite
from django.core.exceptions import ValidationError
from django.db import IntegrityError, close_old_connections, transaction
from django.test import RequestFactory
from django.urls import reverse

from apps.accounts.models import Role
from apps.assessments import programme, services
from apps.assessments.admin import AssessmentPartAdmin, ProgrammeAssessmentAdmin
from apps.assessments.models import Attempt, ProgrammeAssessmentKind
from apps.audit.models import AuditEvent

from .conftest import right_token
from .test_assessments import answer_all, run_in_threads
from .test_exam_sets import admin_user, learner_in, world  # noqa: F401 (fixtures)
from .test_results import answer_all_parts

pytestmark = pytest.mark.django_db


def finish(part, learner, right=None):
    attempt, created = services.start(learner, part)
    assert created
    answer_all(attempt, learner, right=right)
    return services.submit(attempt.pk, learner.pk)


# --- the rule -------------------------------------------------------------------------------------


def test_blank_means_unlimited(make_part, learner):
    part = make_part()
    assert part.max_attempts is None
    for _ in range(4):
        finish(part, learner)
    assert Attempt.objects.filter(user=learner, part=part).count() == 4


def test_the_limit_is_enforced(make_part, learner):
    part = make_part(max_attempts=2)
    finish(part, learner)
    finish(part, learner)
    with pytest.raises(services.AttemptLimitReached):
        services.start(learner, part)
    assert Attempt.objects.filter(user=learner, part=part).count() == 2


def test_an_attempt_in_progress_is_never_cut_off(make_part, learner):
    part = make_part(max_attempts=1)
    first, created = services.start(learner, part)
    again, created_again = services.start(learner, part)  # resumes, even at the limit
    assert created and not created_again and again.pk == first.pk
    answer_all(first, learner, right=5)
    assert services.submit(first.pk, learner.pk).counted


def test_lowering_the_limit_keeps_the_best_attempt(make_part, learner, learner_client):
    part = make_part()
    finish(part, learner, right=4)  # 80%
    finish(part, learner, right=1)
    finish(part, learner, right=2)
    part.max_attempts = 1
    part.save()
    with pytest.raises(services.AttemptLimitReached):
        services.start(learner, part)
    html = learner_client.get(reverse("assess_intro", args=[part.pk])).content.decode()
    assert "<strong>80.0%</strong>" in html
    assert "3 of 1 attempt used" in html and "No attempts left" in html
    assert reverse("assess_start", args=[part.pk]) not in html  # Start is replaced


def test_the_pages_show_attempts_used_and_hide_start_at_the_limit(
    make_part, learner, learner_client
):
    part = make_part(max_attempts=2)
    url = reverse("assess_intro", args=[part.pk])
    html = learner_client.get(url).content.decode()
    assert "0 of 2 attempts used" in html and reverse("assess_start", args=[part.pk]) in html
    attempt = finish(part, learner)
    result = learner_client.get(reverse("attempt_result", args=[attempt.pk])).content.decode()
    assert "Try again" in result
    attempt = finish(part, learner)
    result = learner_client.get(reverse("attempt_result", args=[attempt.pk])).content.decode()
    assert "Try again" not in result
    html = learner_client.get(url).content.decode()
    assert "2 of 2 attempts used" in html and "No attempts left" in html
    response = learner_client.post(reverse("assess_start", args=[part.pk]), follow=True)
    assert "You have used all 2 attempts allowed" in response.content.decode()
    assert Attempt.objects.filter(user=learner, part=part).count() == 2


def test_unlimited_parts_still_say_unlimited(make_part, learner_client):
    part = make_part()
    html = learner_client.get(reverse("assess_intro", args=[part.pk])).content.decode()
    assert "Attempts are unlimited" in html and "attempts used" not in html


# --- concurrency ----------------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_two_parallel_starts_at_the_limit_create_at_most_one_attempt(make_part, learner):
    part = make_part(max_attempts=2)
    finish(part, learner)

    def start():
        close_old_connections()
        return services.start(learner, part)[0].pk

    results, errors = run_in_threads(2, start)
    assert not errors, errors
    assert len(set(results)) == 1  # one created, the other resumed it
    assert Attempt.objects.filter(user=learner, part=part).count() == 2


@pytest.mark.django_db(transaction=True)
def test_parallel_starts_after_the_limit_create_nothing(make_part, learner):
    part = make_part(max_attempts=1)
    finish(part, learner)

    def start():
        close_old_connections()
        return services.start(learner, part)

    results, errors = run_in_threads(5, start)
    assert not results and len(errors) == 5
    assert all(isinstance(e, services.AttemptLimitReached) for e in errors)
    assert Attempt.objects.filter(user=learner, part=part).count() == 1


# --- the final and the pre-test -------------------------------------------------------------------


def test_the_final_takes_a_limit_and_the_pretest_stays_once(
    client,
    world,  # noqa: F811
    make_user,
    make_batch,
    admin_user,  # noqa: F811
):
    parts, sets = world
    learner = learner_in(make_user, make_batch, sets["B"], admin_user)
    pre, _ = programme.start_programme(learner, "pretest")
    services.submit(pre.pk, learner.pk)
    answer_all_parts(learner, parts)
    final = programme.get_assessment(ProgrammeAssessmentKind.FINAL)
    final.max_attempts = 1
    final.save()
    attempt, _ = programme.start_programme(learner, "final")
    for item in attempt.items.all():
        services.save_answer(attempt.pk, learner, item.position, choice=right_token(item))
    services.submit(attempt.pk, learner.pk)
    with pytest.raises(services.AttemptLimitReached):
        programme.start_programme(learner, "final")
    client.force_login(learner)
    html = client.get(reverse("programme_intro", args=["final"])).content.decode()
    assert "1 of 1 attempt used" in html and "No attempts left" in html
    assert reverse("programme_start", args=["final"]) not in html
    result = client.get(reverse("attempt_result", args=[attempt.pk])).content.decode()
    assert "Try again" not in result

    pretest = programme.get_assessment(ProgrammeAssessmentKind.PRETEST)
    pretest.max_attempts = 3
    with pytest.raises(ValidationError):
        pretest.full_clean()
    with pytest.raises(IntegrityError), transaction.atomic():
        pretest.save()


# --- audit ----------------------------------------------------------------------------------------


def test_changing_the_limit_in_the_admin_is_audited(make_part, make_user):
    admin = make_user(role=Role.ADMIN)
    request = RequestFactory().post("/admin/")
    request.user = admin
    part = make_part()
    part_admin = AssessmentPartAdmin(type(part), AdminSite())
    part.max_attempts = 3
    part_admin.save_model(request, part, None, True)
    part_admin.save_model(request, part, None, True)  # unchanged: no second event
    part.max_attempts = None
    part_admin.save_model(request, part, None, True)
    events = AuditEvent.objects.filter(action="assessment.max_attempts_changed").order_by("pk")
    assert [(e.data["old"], e.data["new"]) for e in events] == [(None, 3), (3, None)]
    assert all(e.actor_id == admin.pk and e.target_id == str(part.pk) for e in events)

    final = programme.get_assessment(ProgrammeAssessmentKind.FINAL)
    final.max_attempts = 2
    ProgrammeAssessmentAdmin(type(final), AdminSite()).save_model(request, final, None, True)
    event = AuditEvent.objects.filter(target_type="ProgrammeAssessment").get()
    assert event.data == {"old": None, "new": 2}
