"""Stage 2: parts, the attempt lifecycle, constraints, concurrency and the stale-attempt job."""

import threading
from datetime import timedelta
from decimal import Decimal

import pytest
from django.db import IntegrityError, close_old_connections, connection, transaction
from django.utils import timezone

from apps.assessments import rules, services
from apps.assessments.models import (
    AssessmentPart,
    Attempt,
    AttemptItem,
    AttemptStatus,
)
from apps.audit.models import AuditEvent
from apps.core import periodic
from apps.questions import services as qservices

from .conftest import right_token, wrong_token

pytestmark = pytest.mark.django_db


# --- validate_part --------------------------------------------------------------------------------


def test_a_good_part_validates_and_publishes(make_part):
    part = make_part(questions=12, draw_n=5, min_per_tag=1)
    assert rules.validate_part(part) == []
    assert part.is_published


def test_the_draw_pool_must_be_twice_draw_n(make_part):
    part = make_part(questions=9, draw_n=5, publish=False)
    errors = rules.validate_part(part)
    assert any("at least 10" in e for e in errors)
    with pytest.raises(rules.PartInvalid):
        rules.publish_part(part)
    part.refresh_from_db()
    assert not part.is_published


def test_every_tag_needs_min_per_tag_questions(make_part, make_question):
    part = make_part(questions=12, draw_n=6, min_per_tag=2, publish=False)
    make_question(100, pc="PC4")  # one lonely question in a new tag
    assert any("Tag PC4 has 1" in e for e in rules.validate_part(part))


def test_draw_n_must_leave_room_for_min_per_tag(make_part):
    part = make_part(questions=12, draw_n=2, min_per_tag=1, publish=False)
    assert any("draw_n is too small" in e for e in rules.validate_part(part))


def test_duplicate_questions_block_publishing(make_part, make_question, module1):
    part = make_part(questions=12, draw_n=5, publish=False)
    first = module1.questions.first()
    twin = make_question(200, pc="PC1")
    qservices.add_version(twin, {**first.current_version.body})
    assert any("more than once" in e for e in rules.validate_part(part))


def test_counted_marks_in_a_module_never_exceed_100(make_part, module1):
    make_part(questions=12, name="A", marks=60)
    second = AssessmentPart.objects.create(module=module1, name="B", marks=60, selection="all")
    assert any("more than 100" in e for e in rules.validate_part(second))
    assert rules.module_marks_total(module1) == 120


def test_interactive_parts_wait_for_stage_3(module1):
    part = AssessmentPart.objects.create(module=module1, name="B", family="interactive", marks=50)
    assert rules.validate_part(part)


def test_only_live_questions_are_drawn(make_part, make_question, learner):
    part = make_part(questions=12, selection="all")
    make_question(300, hint=False, live=False)  # a draft with no hint
    attempt, _ = services.start(learner, part)
    stable_ids = set(attempt.items.values_list("question_version__question__stable_id", flat=True))
    assert "M1-T300" not in stable_ids
    assert len(stable_ids) == 12


# --- start, draw, shuffle, tokens ------------------------------------------------------------------


def test_start_draws_n_questions_with_min_per_tag(make_part, learner):
    part = make_part(questions=12, draw_n=6, min_per_tag=2)
    attempt, created = services.start(learner, part)
    assert created and attempt.number == 1 and attempt.items.count() == 6
    pcs = [i.question_version.question.tags["pc"] for i in attempt.items.all()]
    assert {pc: pcs.count(pc) for pc in ("PC1", "PC2", "PC3")} == {"PC1": 2, "PC2": 2, "PC3": 2}
    assert [i.position for i in attempt.items.all()] == [1, 2, 3, 4, 5, 6]


def test_unpublished_parts_cannot_be_started(make_part, learner):
    part = make_part(publish=False)
    with pytest.raises(services.PartNotAvailable):
        services.start(learner, part)


def test_option_tokens_are_random_one_off_and_say_nothing_about_the_key(make_part, learner):
    part = make_part(questions=12, draw_n=5)
    attempt, _ = services.start(learner, part)
    internal = {
        "o1",
        "o2",
        "o3",
        "o4",
        "o5",
        "o6",
        "a",
        "b",
        "c",
        "d",
        "A",
        "B",
        "C",
        "D",
        "0",
        "1",
        "2",
        "3",
    }
    seen = set()
    for item in attempt.items.all():
        tokens = item.option_map["tokens"]
        assert len(tokens) == 4 and list(tokens) != list(tokens.values())
        assert set(item.option_map["order"]) == set(tokens)
        assert not (set(tokens) & internal)  # never an internal id or a position
        assert all(len(t) >= 10 for t in tokens)
        assert not (set(tokens) & seen)  # unique across the whole attempt
        seen |= set(tokens)
    # A second attempt gets different tokens for the same question.
    services.submit(attempt.pk, learner.pk)
    second, _ = services.start(learner, part)
    assert not (seen & {t for i in second.items.all() for t in i.option_map["tokens"]})


def test_the_right_answer_is_not_always_in_the_same_place(make_part, learner):
    part = make_part(questions=30, selection="all")
    attempt, _ = services.start(learner, part)
    positions = set()
    for item in attempt.items.all():
        correct = item.question_version.body["correct"]
        order_keys = [item.option_map["tokens"][t] for t in item.option_map["order"]]
        positions.add(order_keys.index(correct))
    assert len(positions) > 1  # the source lists the right answer second; shuffling moves it


def test_a_second_attempt_prefers_questions_not_seen_before(make_part, learner):
    part = make_part(questions=12, draw_n=5, min_per_tag=1)
    first, _ = services.start(learner, part)
    first_ids = set(first.items.values_list("question_version__question_id", flat=True))
    services.submit(first.pk, learner.pk)
    second, created = services.start(learner, part)
    second_ids = set(second.items.values_list("question_version__question_id", flat=True))
    assert created and second.number == 2 and not (first_ids & second_ids)


def test_selection_all_keeps_order_and_all_shuffled_keeps_every_question(make_part, learner):
    part = make_part(questions=6, selection="all", name="All")
    attempt, _ = services.start(learner, part)
    ids = list(attempt.items.values_list("question_version__question__stable_id", flat=True))
    assert ids == sorted(ids) and len(ids) == 6
    shuffled = make_part(questions=0, selection="all_shuffled", name="Shuffled", marks=40)
    attempt2, _ = services.start(learner, shuffled)
    assert attempt2.items.count() == 6


# --- resume ---------------------------------------------------------------------------------------


def test_starting_again_resumes_the_attempt_in_progress(make_part, learner):
    part = make_part()
    first, created = services.start(learner, part)
    again, created_again = services.start(learner, part)
    assert created and not created_again and again.pk == first.pk
    assert Attempt.objects.filter(user=learner, part=part).count() == 1


def test_questions_are_frozen_at_start_even_if_the_question_changes_later(make_part, learner):
    part = make_part(questions=12, draw_n=5)
    attempt, _ = services.start(learner, part)
    item = attempt.items.first()
    question = item.question_version.question
    qservices.add_version(
        question, {**item.question_version.body, "stem": "Invented: edited later?"}
    )
    question.points = Decimal("5")
    question.save()
    item.refresh_from_db()
    assert item.question_version.body["stem"].startswith("Invented question number")
    assert item.points == Decimal("1.00")


# --- answers ---------------------------------------------------------------------------------------


def test_save_answer_stores_the_token_and_touches_last_saved(make_part, learner):
    part = make_part()
    attempt, _ = services.start(learner, part)
    item = attempt.items.get(position=1)
    before = attempt.last_saved_at
    saved = services.save_answer(attempt.pk, learner, 1, choice=right_token(item))
    assert saved.response == {"choice": right_token(item)}
    attempt.refresh_from_db()
    assert attempt.last_saved_at > before


def test_save_answer_refuses_unknown_tokens_positions_and_strangers(make_part, learner, make_user):
    part = make_part()
    attempt, _ = services.start(learner, part)
    with pytest.raises(services.InvalidAnswer):
        services.save_answer(attempt.pk, learner, 1, choice="not-a-token")
    with pytest.raises(services.InvalidAnswer):
        services.save_answer(attempt.pk, learner, 99, choice="x")
    with pytest.raises(Attempt.DoesNotExist):
        services.save_answer(attempt.pk, make_user(), 1, choice="x")
    assert not attempt.items.get(position=1).answered


def test_the_review_flag_is_kept_with_the_answer(make_part, learner):
    attempt, _ = services.start(learner, make_part())
    item = attempt.items.get(position=2)
    services.save_answer(attempt.pk, learner, 2, choice=wrong_token(item), flag=True)
    services.save_answer(attempt.pk, learner, 2, flag=False)
    assert attempt.items.get(position=2).response == {"choice": wrong_token(item), "flag": False}


def test_answers_cannot_change_after_submit(make_part, learner):
    attempt, _ = services.start(learner, make_part())
    services.submit(attempt.pk, learner.pk)
    with pytest.raises(services.AttemptClosed):
        services.save_answer(attempt.pk, learner, 1, choice="x")


# --- submit and scoring ------------------------------------------------------------------------------


def answer_all(attempt, learner, right=None, skip=()):
    """Answer items 1..n: the first `right` correctly, the rest wrongly (positions in `skip` blank)."""
    for item in attempt.items.all():
        if item.position in skip:
            continue
        token = right_token(item) if item.position <= (right or 0) else wrong_token(item)
        services.save_answer(attempt.pk, learner, item.position, choice=token)


def test_submit_scores_on_the_server_from_the_frozen_versions(make_part, learner):
    attempt, _ = services.start(learner, make_part(questions=12, draw_n=5))
    answer_all(attempt, learner, right=3)
    done = services.submit(attempt.pk, learner.pk)
    assert done.status == AttemptStatus.SUBMITTED
    assert done.score == Decimal("60.0") and done.all_answered and done.counted
    assert not done.gate_breached
    assert [i.score for i in done.items.all()] == [1, 1, 1, 0, 0]
    assert done.submitted_at is not None


def test_unanswered_questions_score_zero_and_mean_not_all_answered(make_part, learner):
    attempt, _ = services.start(learner, make_part(questions=12, draw_n=5))
    answer_all(attempt, learner, right=5, skip=(4, 5))
    done = services.submit(attempt.pk, learner.pk)
    assert done.score == Decimal("60.0") and not done.all_answered and done.counted


def test_points_weight_the_score(make_part, make_question, module1, learner):
    from apps.assessments.models import AssessmentPart

    heavy = make_question(1, points=3)
    make_question(2, points=1)
    part = AssessmentPart.objects.create(module=module1, name="Weighted", marks=50, selection="all")
    rules.publish_part(part)
    attempt, _ = services.start(learner, part)
    first = attempt.items.get(question_version__question=heavy)
    services.save_answer(attempt.pk, learner, first.position, choice=right_token(first))
    assert services.submit(attempt.pk, learner.pk).score == Decimal("75.0")  # 3 of 4 points


def test_a_gate_choice_shows_the_score_but_never_counts(make_part, make_question, module1, learner):
    from apps.assessments.models import AssessmentPart

    for n in range(1, 4):
        make_question(n, gate=[1])  # option o1 would endanger a citizen
    part = AssessmentPart.objects.create(module=module1, name="Gate", marks=50, selection="all")
    rules.publish_part(part)
    attempt, _ = services.start(learner, part)
    for item in attempt.items.all():
        risky = next(t for t, k in item.option_map["tokens"].items() if k == "o1")
        services.save_answer(attempt.pk, learner, item.position, choice=risky)
    done = services.submit(attempt.pk, learner.pk)
    assert done.gate_breached and not done.counted and done.score == Decimal("0.0")
    assert all(i.gate_flag for i in done.items.all())


def test_submit_twice_gives_one_result(make_part, learner):
    attempt, _ = services.start(learner, make_part())
    answer_all(attempt, learner, right=2)
    first = services.submit(attempt.pk, learner.pk)
    again = services.submit(attempt.pk, learner.pk)
    assert again.pk == first.pk and again.score == first.score
    assert again.submitted_at == first.submitted_at
    assert AuditEvent.objects.filter(action="attempt.submitted").count() == 1


def test_audit_events_hold_ids_not_names(make_part, learner):
    attempt, _ = services.start(learner, make_part())
    services.submit(attempt.pk, learner.pk)
    for event in AuditEvent.objects.filter(action__startswith="attempt."):
        text = str(event.data)
        assert learner.email not in text and learner.profile.certificate_name not in text
        assert event.actor_id == learner.pk


# --- database constraints ---------------------------------------------------------------------------


def test_only_one_attempt_in_progress_per_learner_and_part(make_part, learner):
    part = make_part()
    services.start(learner, part)
    with pytest.raises(IntegrityError), transaction.atomic():
        Attempt.objects.create(user=learner, part=part, number=2)


def test_attempt_numbers_are_unique_per_learner_and_part(make_part, learner):
    part = make_part()
    attempt, _ = services.start(learner, part)
    services.submit(attempt.pk, learner.pk)
    with pytest.raises(IntegrityError), transaction.atomic():
        Attempt.objects.create(user=learner, part=part, number=1, status="submitted")


def test_a_finished_attempt_does_not_block_a_new_one(make_part, learner):
    part = make_part()
    attempt, _ = services.start(learner, part)
    services.submit(attempt.pk, learner.pk)
    second, created = services.start(learner, part)
    assert created and second.number == 2


def test_an_attempt_belongs_to_a_part_or_a_programme_assessment_not_neither(learner):
    with pytest.raises(IntegrityError), transaction.atomic():
        Attempt.objects.create(user=learner, number=1)


def test_item_positions_are_unique_and_scores_stay_between_0_and_1(make_part, learner):
    attempt, _ = services.start(learner, make_part())
    item = attempt.items.first()
    with pytest.raises(IntegrityError), transaction.atomic():
        AttemptItem.objects.create(
            attempt=attempt,
            position=1,
            question_version=item.question_version,
            points=1,
            option_map={},
        )
    with pytest.raises(IntegrityError), transaction.atomic():
        AttemptItem.objects.filter(pk=item.pk).update(score=Decimal("1.5"))


# --- concurrency (real threads, real transactions) ------------------------------------------------------


def run_in_threads(count, target):
    barrier = threading.Barrier(count)
    results, errors = [], []

    def worker():
        try:
            barrier.wait(timeout=10)
            results.append(target())
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)
        finally:
            connection.close()

    threads = [threading.Thread(target=worker) for _ in range(count)]
    [t.start() for t in threads]
    [t.join(timeout=30) for t in threads]
    return results, errors


@pytest.mark.django_db(transaction=True)
def test_two_parallel_starts_create_one_attempt(make_part, learner):
    part = make_part()

    def start():
        close_old_connections()
        attempt, created = services.start(learner, part)
        return attempt.pk, created

    results, errors = run_in_threads(2, start)
    assert not errors, errors
    assert len({pk for pk, _ in results}) == 1
    assert sorted(created for _, created in results) == [False, True]
    assert Attempt.objects.filter(user=learner, part=part).count() == 1
    assert AttemptItem.objects.filter(attempt__user=learner).count() == 5


@pytest.mark.django_db(transaction=True)
def test_five_parallel_starts_still_create_one_attempt(make_part, learner):
    part = make_part()
    results, errors = run_in_threads(5, lambda: services.start(learner, part)[0].pk)
    assert not errors, errors
    assert len(set(results)) == 1 and Attempt.objects.count() == 1


@pytest.mark.django_db(transaction=True)
def test_two_parallel_submits_score_once(make_part, learner):
    part = make_part()
    attempt, _ = services.start(learner, part)
    answer_all(attempt, learner, right=2)
    results, errors = run_in_threads(2, lambda: services.submit(attempt.pk, learner.pk).score)
    assert not errors, errors
    assert results == [Decimal("40.0"), Decimal("40.0")]
    assert AuditEvent.objects.filter(action="attempt.submitted").count() == 1


# --- stale attempts: the daily job ----------------------------------------------------------------------


def age(attempt, days):
    Attempt.objects.filter(pk=attempt.pk).update(
        last_saved_at=timezone.now() - timedelta(days=days)
    )


def test_stale_attempts_are_auto_submitted_with_their_saved_answers(
    make_part, make_user, make_batch
):
    part = make_part()
    stale_user, fresh_user = make_user(batch=make_batch()), make_user(batch=make_batch())
    stale, _ = services.start(stale_user, part)
    answer_all(stale, stale_user, right=2, skip=(5,))
    fresh, _ = services.start(fresh_user, part)
    age(stale, 8)
    age(fresh, 6)
    assert services.auto_submit_stale() == 1
    stale.refresh_from_db()
    fresh.refresh_from_db()
    assert stale.status == AttemptStatus.AUTO_SUBMITTED and stale.score == Decimal("40.0")
    assert not stale.all_answered and stale.counted and stale.submitted_at
    assert fresh.status == AttemptStatus.IN_PROGRESS
    assert AuditEvent.objects.filter(action="system.auto_submit_stale").get().data == {"count": 1}


def test_auto_submit_is_repeat_safe(make_part, learner):
    attempt, _ = services.start(learner, make_part())
    age(attempt, 9)
    assert services.auto_submit_stale() == 1
    assert services.auto_submit_stale() == 0


def test_one_failing_attempt_does_not_stop_the_others(
    make_part, make_user, make_batch, monkeypatch
):
    part = make_part()
    users = [make_user(batch=make_batch()) for _ in range(3)]
    attempts = [services.start(u, part)[0] for u in users]
    for a in attempts:
        age(a, 8)
    real = services.submit

    def flaky(attempt_id, user_id, **kwargs):
        if attempt_id == attempts[0].pk:
            raise RuntimeError("boom")
        return real(attempt_id, user_id, **kwargs)

    monkeypatch.setattr(services, "submit", flaky)
    assert services.auto_submit_stale() == 2
    assert Attempt.objects.get(pk=attempts[0].pk).status == AttemptStatus.IN_PROGRESS


def test_the_periodic_runner_has_the_auto_submit_job(make_part, learner):
    attempt, _ = services.start(learner, make_part())
    age(attempt, 8)
    at = timezone.now().replace(hour=12)
    result = periodic.run_due(at)
    assert result["auto_submit_stale_attempts"] == "ok"
    assert Attempt.objects.get(pk=attempt.pk).status == AttemptStatus.AUTO_SUBMITTED
    assert periodic.run_due(at)["auto_submit_stale_attempts"] == "skipped"  # once a day
