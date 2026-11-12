"""Stage 5: results policy, unlock rules, the pre-test, the final, knowledge gain and the dashboard.
Invented learners and questions only."""

import re
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Role, UserStatus
from apps.assessments import examsets, programme, rules, services
from apps.assessments.models import (
    AssessmentPart,
    Attempt,
    AttemptItem,
    AttemptStatus,
    ExamSet,
    ExamSetItem,
    ProgrammeAssessmentKind,
)
from apps.content.models import Module
from apps.questions.models import PoolLocked, Question
from apps.results import insights, policy
from apps.results.policy import compute_results, round1

from .conftest import HINT, right_token, wrong_token

pytestmark = pytest.mark.django_db
D = Decimal


# --- helpers ---------------------------------------------------------------------------------------


def make_parts(numbers=range(1, 10), published=True):
    """Two counted parts of 50 marks in each of these modules."""
    parts = {}
    for n in numbers:
        module, _ = Module.objects.get_or_create(
            number=n, defaults={"slug": f"module-{n}", "title_key": "x", "order": n}
        )
        module.title = f"Invented module {n}"
        module.save()
        parts[n] = [
            AssessmentPart.objects.create(
                module=module, name=name, marks=50, selection="all", is_published=published
            )
            for name in ("Part A", "Part B")
        ]
    # Modules without parts here are not part of this test world (counted modules with no published
    # assessment would be a course-setup gap, which has its own tests below).
    Module.objects.exclude(number__in=list(numbers)).update(counted=False)
    return parts


def attempt(
    user, *, part=None, kind=None, number=1, score="0", counted=True, answered=True, gated=False
):
    pa = programme.get_assessment(kind) if kind else None
    return Attempt.objects.create(
        user=user, part=part, programme_assessment=pa, number=number,
        status=AttemptStatus.SUBMITTED, score=D(score), counted=counted and not gated,
        all_answered=answered, gate_breached=gated, submitted_at=timezone.now(),
    )  # fmt: skip


def answer_all_parts(user, parts, score="60"):
    for plist in parts.values():
        for p in plist:
            attempt(user, part=p, score=score)


# --- the worked example (§10.3) and the rounding boundaries -------------------------------------------


def test_worked_example_from_the_architecture_matches_exactly():
    """Module 4 enters the mean at full precision (68.666…); the nine modules, the final and the
    overall come out as 63.0, 61.0 and 62.0, grade B."""
    third = D(1) / 3
    m4 = policy.ModuleResult(
        4,
        "m4",
        [
            policy.PartResult(1, "A", 50, best=D("220") * third),
            policy.PartResult(2, "B", 50, best=D("64.0")),
        ],
    )
    assert m4.raw == (50 * D("220") * third + 50 * D("64.0")) / 100
    assert m4.shown == D("68.7") and m4.passed
    others = [("72.0"), ("55.0"), ("64.2"), None, ("51.0"), ("66.0"), ("70.0"), ("58.0"), ("62.0")]
    modules = []
    for n, pct in enumerate(others, start=1):
        if pct is None:
            modules.append(m4)
        else:
            modules.append(
                policy.ModuleResult(n, f"m{n}", [policy.PartResult(n, "A", 100, best=D(pct))])
            )
    result = policy.Result(user_id=1, modules=modules, final_best=D("61.0"))
    assert result.modules_shown == D("63.0")
    assert result.overall_shown == D("62.0") and result.grade == "B"
    assert result.overall_raw == D("0.5") * result.modules_raw + D("30.5")


def test_worked_example_through_real_attempts(learner):
    """The same example from stored attempts: a gated 81.5 does not count, answered still does."""
    parts = make_parts()
    pct = {1: "72.0", 2: "55.0", 3: "64.2", 5: "51.0", 6: "66.0", 7: "70.0", 8: "58.0", 9: "62.0"}
    for n, plist in parts.items():
        if n == 4:
            continue
        for p in plist:
            attempt(learner, part=p, score=pct[n])
    a, b = parts[4]
    attempt(learner, part=a, number=1, score="53.3")
    attempt(learner, part=a, number=2, score="73.3")
    attempt(learner, part=b, number=1, score="81.5", gated=True)  # shown, not counted
    attempt(learner, part=b, number=2, score="64.0")
    attempt(learner, kind=ProgrammeAssessmentKind.FINAL, score="61.0")
    r = compute_results([learner.pk])[learner.pk]
    assert r.modules[3].shown == D("68.7") and r.modules[3].parts[1].best == D("64.0")
    assert r.modules_shown == D("63.0") and r.final_shown == D("61.0")
    assert r.overall_shown == D("62.0") and r.grade == "B"


@pytest.mark.parametrize(
    ("raw", "shown", "passes"),
    [
        ("49.94", "49.9", False),
        ("49.95", "50.0", True),
        ("50.0", "50.0", True),
        ("49.949", "49.9", False),
    ],
)
def test_pass_boundaries_compare_after_rounding(raw, shown, passes):
    assert round1(D(raw)) == D(shown)
    module = policy.ModuleResult(1, "m", [policy.PartResult(1, "A", 100, best=D(raw))])
    assert module.passed is passes


@pytest.mark.parametrize(
    ("overall", "letter"),
    [
        ("79.95", "A"),
        ("79.94", "B"),
        ("89.95", "A+"),
        ("60.0", "B"),
        ("59.95", "B"),
        ("59.94", "C"),
        ("49.94", "Not yet"),
    ],
)
def test_grade_boundaries(overall, letter):
    assert policy.grade(D(overall)) == letter


def test_bands():
    assert [policy.band(D(x)) for x in ("75", "74.95", "74.94", "50", "49.94")] == [
        "strong",
        "strong",
        "ok",
        "ok",
        "needs_work",
    ]


# --- unlock rules (§10.2), journey 7 ------------------------------------------------------------------


def test_journey7_one_part_submitted_with_blanks_keeps_the_final_locked_with_the_reason(learner):
    parts = make_parts(range(1, 10))  # 18 parts
    flat = [p for plist in parts.values() for p in plist]
    for i, p in enumerate(flat):
        attempt(learner, part=p, score="70", answered=(i != 5))  # one has blanks
    attempt(learner, kind=ProgrammeAssessmentKind.PRETEST, score="40")
    result = compute_results([learner.pk])[learner.pk]
    assert (
        not result.final_unlocked
        and sum(
            1
            for p in flat
            if not result.modules[(p.module.number) - 1]
            .parts[0 if p.name == "Part A" else 1]
            .answered
        )
        == 1
    )
    reasons = programme.final_locked_reasons(learner)
    assert (
        len(reasons) == 1
        and "Module 3, Part B" in reasons[0]
        and "every question answered" in reasons[0]
    )
    with pytest.raises(programme.Locked):
        programme.start_programme(learner, "final")


def test_the_final_stays_locked_until_the_pretest_is_done_even_if_every_part_is_answered(learner):
    parts = make_parts([1, 2])
    answer_all_parts(learner, parts)
    reasons = programme.final_locked_reasons(learner)
    assert any("pre-test" in r.lower() for r in reasons)
    attempt(learner, kind=ProgrammeAssessmentKind.PRETEST)
    assert programme.final_locked_reasons(learner) == []


def test_a_gated_submission_still_counts_as_answered_for_the_unlock(learner):
    parts = make_parts([1])
    attempt(learner, part=parts[1][0], score="80", gated=True)
    attempt(learner, part=parts[1][1], score="80")
    r = compute_results([learner.pk])[learner.pk]
    assert r.parts_all_answered and r.modules[0].parts[0].best == 0  # answered, but not counted


def test_unpublished_counted_parts_keep_the_final_locked_as_a_setup_problem(learner):
    make_parts([1], published=False)
    attempt(learner, kind=ProgrammeAssessmentKind.PRETEST)
    r = compute_results([learner.pk])[learner.pk]
    assert r.setup_gaps and not r.final_unlocked and not r.eligible
    reasons = programme.final_locked_reasons(learner)
    assert (
        len(reasons) == 1
        and "Course setup is incomplete" in reasons[0]
        and "Module 1" in reasons[0]
    )
    with pytest.raises(programme.Locked, match="Course setup is incomplete"):
        programme.start_programme(learner, "final")


def test_a_counted_module_with_no_published_assessment_keeps_the_final_locked(learner):
    make_parts([1])  # module 1 is fine; module 2 stays counted but has no parts
    Module.objects.filter(number=2).update(counted=True)
    answer_all_parts(learner, {1: AssessmentPart.objects.filter(module__number=1)})
    attempt(learner, kind=ProgrammeAssessmentKind.PRETEST)
    attempt(learner, kind=ProgrammeAssessmentKind.FINAL, score="95")
    r = compute_results([learner.pk])[learner.pk]
    assert not r.final_unlocked and not r.eligible
    assert any(
        "Course setup is incomplete" in b and "Module 2 has no published assessment" in b
        for b in r.blockers
    )
    assert any("Course setup is incomplete" in x for x in programme.final_locked_reasons(learner))


def test_the_dashboard_explains_that_course_setup_is_incomplete(learner_client, learner):
    make_parts([1], published=False)
    learner.profile.pretest_prompted_at = timezone.now()
    learner.profile.save()
    html = learner_client.get(reverse("start")).content.decode()
    assert "Course setup is incomplete" in html and "Locked" in html


# --- eligibility and blockers ----------------------------------------------------------------------------


def passing(learner, parts, final="70"):
    answer_all_parts(learner, parts, "70")
    attempt(learner, kind=ProgrammeAssessmentKind.PRETEST, score="30")
    attempt(learner, kind=ProgrammeAssessmentKind.FINAL, score=final)


def test_eligible_needs_verified_email_active_status_and_every_pass(learner):
    parts = make_parts([1, 2])
    passing(learner, parts)
    assert compute_results([learner.pk])[learner.pk].eligible
    from allauth.account.models import EmailAddress

    EmailAddress.objects.filter(user=learner).update(verified=False)
    r = compute_results([learner.pk])[learner.pk]
    assert not r.eligible and any("Verify your email" in b for b in r.blockers)
    EmailAddress.objects.filter(user=learner).update(verified=True)
    learner.status = UserStatus.PENDING_GUARDIAN
    learner.save()
    assert not compute_results([learner.pk])[learner.pk].eligible


def test_one_weak_module_or_final_blocks_eligibility_with_a_plain_message(learner):
    parts = make_parts([1, 2])
    answer_all_parts(learner, {1: parts[1]}, "70")
    attempt(learner, part=parts[2][0], score="52")
    attempt(learner, part=parts[2][1], score="36")
    attempt(learner, kind=ProgrammeAssessmentKind.PRETEST)
    attempt(learner, kind=ProgrammeAssessmentKind.FINAL, score="45")
    r = compute_results([learner.pk])[learner.pk]
    assert not r.eligible
    assert any("Module 2 is at 44.0%" in b and "52.0%" in b and "36.0%" in b for b in r.blockers)
    assert any("Your best final is 45.0%" in b for b in r.blockers)


def test_compute_results_handles_many_users_and_isolates_them(learner, make_user, make_batch):
    parts = make_parts([1])
    other = make_user(batch=make_batch())
    answer_all_parts(learner, parts, "80")
    results = compute_results([learner.pk, other.pk])
    assert results[learner.pk].modules[0].shown == D("80.0") and results[other.pk].modules[
        0
    ].shown == D("0.0")


# --- drawing the pre-test and the final from the batch's exam set, journey 11 ---------------------------


def final_questions(make_question, module, count, start=1):
    return [
        make_question(start + i, module=module, pool="final", pc=f"PC{1 + i % 3}")
        for i in range(count)
    ]


def make_exam_set(code, by_module, admin, release=True):
    """An invented set: the first two questions of each module are the shared pre-test ones."""
    exam_set = ExamSet.objects.create(code=code, name=f"Invented set {code}")
    for questions in by_module:
        for i, q in enumerate(questions):
            ExamSetItem.objects.create(exam_set=exam_set, question=q, in_pretest=i < 2)
    if release:
        assert examsets.release(exam_set, admin) == []
    return exam_set


@pytest.fixture
def admin_user(make_user):
    return make_user(role=Role.ADMIN)


@pytest.fixture
def exam(make_question, learner, admin_user):
    """Two modules, blueprint 3 per module, and the learner's batch given released Set B
    (3 final-pool questions per module, 2 of them shared with the pre-test)."""
    parts = make_parts([1, 2])
    final = programme.get_assessment(ProgrammeAssessmentKind.FINAL)
    final.blueprint = {"per_module": {"1": 3, "2": 3}, "anchors": []}
    final.save()
    set_b = make_exam_set(
        "B",
        [
            final_questions(make_question, parts[1][0].module, 3, start=1),
            final_questions(make_question, parts[2][0].module, 3, start=101),
        ],
        admin_user,
    )
    examsets.assign(learner.enrolment.batch, set_b, admin_user)
    return parts


def set_ids(code, pretest=None):
    items = ExamSetItem.objects.filter(exam_set__code=code)
    if pretest is not None:
        items = items.filter(in_pretest=pretest)
    return set(items.values_list("question_id", flat=True))


def attempt_ids(a):
    return {i.question_version.question_id for i in a.items.select_related("question_version")}


def test_the_pretest_is_the_sets_shared_questions_only_once_and_resumable(learner, exam):
    attempt1, created = programme.start_programme(learner, "pretest")
    assert created and attempt1.items.count() == 4
    assert attempt_ids(attempt1) == set_ids("B", pretest=True)
    again, created = programme.start_programme(learner, "pretest")
    assert again.pk == attempt1.pk and not created  # resumable
    services.submit(attempt1.pk, learner.pk)
    with pytest.raises(programme.AlreadyDone):
        programme.start_programme(learner, "pretest")


def test_the_final_is_the_whole_set_shuffled_and_includes_every_shared_question(learner, exam):
    answer_all_parts(learner, exam)
    attempt(learner, kind=ProgrammeAssessmentKind.PRETEST)
    orders = set()
    for _ in range(6):
        a, _ = programme.start_programme(learner, "final")
        items = list(a.items.select_related("question_version__question__module"))
        per = {}
        for i in items:
            n = i.question_version.question.module.number
            per[n] = per.get(n, 0) + 1
        assert per == {1: 3, 2: 3}
        assert attempt_ids(a) == set_ids("B")  # never a question from another set
        assert set_ids("B", pretest=True) <= attempt_ids(a)
        orders.add(tuple(i.question_version.question_id for i in items))
        services.submit(a.pk, learner.pk)
    assert len(orders) > 1  # shuffled within the set


def test_the_final_cooldown_setting_is_honoured(learner, exam):
    answer_all_parts(learner, exam)
    attempt(learner, kind=ProgrammeAssessmentKind.PRETEST)
    final = programme.get_assessment("final")
    final.cooldown_hours = 2
    final.save()
    a, _ = programme.start_programme(learner, "final")
    services.submit(a.pk, learner.pk)
    with pytest.raises(programme.Locked, match="wait 2 hours"):
        programme.start_programme(learner, "final")
    assert final.cooldown_hours == 2 and programme.get_assessment("final").cooldown_hours == 2


def test_journey11_a_final_result_shows_overall_and_bands_only(learner_client, learner, exam):
    answer_all_parts(learner, exam)
    attempt(learner, kind=ProgrammeAssessmentKind.PRETEST)
    a, _ = programme.start_programme(learner, "final")
    for item in a.items.all():
        learner_client.post(
            reverse("attempt_answer", args=[a.pk]),
            {"position": item.position, "choice": right_token(item)},
            HTTP_HX_REQUEST="true",
        )
    learner_client.post(reverse("attempt_submit", args=[a.pk]))
    html = learner_client.get(reverse("attempt_result", args=[a.pk])).content.decode()
    assert "100.0%" in html and "Strong" in html and "Module 1" in html and "Module 2" in html
    assert (
        "HINT-" not in html and "RIGHT-" not in html and "WRONG-" not in html
    )  # no answers, hints or options
    assert "Invented question number" not in html  # not even the questions
    assert "Hint" not in html and "Right" not in html and "Not quite" not in html


def test_bands_follow_the_items_of_each_module(learner, exam):
    answer_all_parts(learner, exam)
    attempt(learner, kind=ProgrammeAssessmentKind.PRETEST)
    a, _ = programme.start_programme(learner, "final")
    for item in a.items.select_related("question_version__question__module"):
        number = item.question_version.question.module.number
        services.save_answer(
            a.pk,
            learner,
            item.position,
            choice=right_token(item) if number == 1 else wrong_token(item),
        )
    services.submit(a.pk, learner.pk)
    assert insights.final_bands(a) == [
        {"module": 1, "band": "strong"},
        {"module": 2, "band": "needs_work"},
    ]


def test_the_pretest_result_shows_the_score_only_never_feedback(learner_client, learner, exam):
    a, _ = programme.start_programme(learner, "pretest")
    for item in a.items.all():
        services.save_answer(a.pk, learner, item.position, choice=right_token(item))
    learner_client.post(reverse("attempt_submit", args=[a.pk]))
    html = learner_client.get(reverse("attempt_result", args=[a.pk])).content.decode()
    assert "100.0%" in html and "Pre-test done" in html
    assert "HINT-" not in html and "RIGHT-" not in html and "Invented question number" not in html
    assert "Strong" not in html and "Needs work" not in html  # no module bands either


@pytest.mark.parametrize("kind", ["pretest", "final"])
def test_a_programme_exam_page_has_no_key_in_it(learner_client, learner, exam, kind):
    if kind == "final":
        answer_all_parts(learner, exam)
        attempt(learner, kind=ProgrammeAssessmentKind.PRETEST)
    a, _ = programme.start_programme(learner, kind)
    html = learner_client.get(reverse("attempt_page", args=[a.pk])).content.decode()
    assert "HINT-" not in html and '"correct"' not in html
    assert 'value="o2"' not in html and 'data-choice="o2"' not in html  # never the raw ids


# --- the pool rule (§11) ------------------------------------------------------------------------------------------


def test_a_question_shown_in_a_non_final_attempt_cannot_move_into_the_final_pool(
    learner, make_question, make_part
):
    part = make_part()
    attempt_, _ = services.start(learner, part)
    shown = Question.objects.get(pk=attempt_.items.first().question_version.question_id)
    shown.pool = "final"
    with pytest.raises(PoolLocked):
        shown.save()
    assert Question.objects.get(pk=shown.pk).pool == "module_quiz"
    fresh = Question.objects.exclude(
        pk__in=AttemptItem.objects.values("question_version__question")
    ).first()
    fresh.pool = "final"
    fresh.save()  # never shown: allowed
    assert Question.objects.get(pk=fresh.pk).pool == "final"


def test_a_question_shown_only_in_programme_exams_stays_in_the_final_pool(learner, exam):
    answer_all_parts(learner, exam)
    attempt(learner, kind=ProgrammeAssessmentKind.PRETEST)
    a, _ = programme.start_programme(learner, "final")
    q = Question.objects.get(pk=a.items.first().question_version.question_id)
    q.save()  # unchanged pool: fine
    assert Question.objects.get(pk=q.pk).pool == "final"


# --- knowledge gain ------------------------------------------------------------------------------------------------


def test_knowledge_gain_compares_the_same_shared_questions(learner, exam):
    pre, _ = programme.start_programme(learner, "pretest")
    for n, item in enumerate(pre.items.all()):
        services.save_answer(
            pre.pk, learner, item.position, choice=right_token(item) if n < 1 else wrong_token(item)
        )
    services.submit(pre.pk, learner.pk)  # 1 of 4 shared questions right = 25.0
    assert insights.knowledge_gain(learner) is None  # needs a final too
    answer_all_parts(learner, exam)
    shared = set_ids("B", pretest=True)
    first, _ = programme.start_programme(learner, "final")
    for item in first.items.select_related("question_version"):
        right = item.question_version.question_id in shared
        services.save_answer(
            first.pk,
            learner,
            item.position,
            choice=right_token(item) if right else wrong_token(item),
        )
    services.submit(first.pk, learner.pk)  # all shared right (the others wrong) = 100.0
    assert insights.knowledge_gain(learner) == D("75.0")
    second, _ = programme.start_programme(learner, "final")  # a later attempt never changes it
    for item in second.items.all():
        services.save_answer(second.pk, learner, item.position, choice=wrong_token(item))
    services.submit(second.pk, learner.pk)
    assert insights.knowledge_gain(learner) == D("75.0")


# --- weakest PCs -----------------------------------------------------------------------------------------------------


def test_weakest_pcs_come_from_counted_mcq_attempts(learner, make_part):
    part = make_part(questions=12, draw_n=6, min_per_tag=2)
    a, _ = services.start(learner, part)
    for item in a.items.select_related("question_version__question"):
        weak = item.question_version.question.tags["pc"] == "PC2"
        services.save_answer(
            a.pk, learner, item.position, choice=wrong_token(item) if weak else right_token(item)
        )
    services.submit(a.pk, learner.pk)
    rows = insights.weakest_pcs(learner)
    assert rows[0]["pc"] == "PC2" and rows[0]["percent"] == D("0.0")


# --- the dashboard (§15): new, mid-way, eligible --------------------------------------------------------------------


def test_the_dashboard_for_a_new_learner(learner_client, learner, exam):
    learner.profile.pretest_prompted_at = timezone.now()
    learner.profile.save()
    html = learner_client.get(reverse("start")).content.decode()
    assert "Hello," in html and "left before your final" in html
    assert "Locked" in html and "Take the short pre-test" in html
    assert "Invented module 1" in html


def test_the_pretest_is_offered_once_after_the_first_sign_in(learner_client, learner, exam):
    first = learner_client.get(reverse("start"))
    assert first.status_code == 302 and first["Location"] == reverse(
        "programme_intro", args=["pretest"]
    )
    second = learner_client.get(reverse("start"))  # "Later": the dashboard, with its card
    assert second.status_code == 200 and b"Take the pre-test" in second.content
    learner.profile.refresh_from_db()
    assert learner.profile.pretest_prompted_at is not None


def test_the_dashboard_midway(learner_client, learner, exam):
    learner.profile.pretest_prompted_at = timezone.now()
    learner.profile.save()
    attempt(learner, part=exam[1][0], score="65")
    html = learner_client.get(reverse("start")).content.decode()
    assert "65.0%" in html and "1 finished" in html and "Locked" in html
    assert "Module 1: Part B" in html  # still to do, listed before the finished items
    assert html.index("Module 1: Part B") < html.index("1 finished")


def test_the_dashboard_when_eligible(learner_client, learner, exam):
    learner.profile.pretest_prompted_at = timezone.now()
    learner.profile.save()
    passing(learner, exam)
    html = learner_client.get(reverse("start")).content.decode()
    assert "You have met every requirement" in html and "You are eligible" in html
    assert "70.0%" in html and "Try the final again" in html
    assert "What is stopping your certificate" not in html


def test_the_dashboard_shows_the_blocker_in_plain_words(learner_client, learner, exam):
    learner.profile.pretest_prompted_at = timezone.now()
    learner.profile.save()
    attempt(learner, part=exam[1][0], score="30")
    attempt(learner, part=exam[1][1], score="30")
    html = learner_client.get(reverse("start")).content.decode()
    assert "What is stopping your certificate" in html and "Module 1 is at 30.0%" in html


def test_mentors_are_not_sent_to_the_dashboard(mentor_client):
    assert mentor_client.get(reverse("start"))["Location"] == reverse("mentor_home")


_ = (HINT, rules)


# --- review fixes: unrounded combination, pre-test feedback ---------------------------------------------------


def scored_attempt(user, part, right, total, number=1):
    """An attempt with real question-level marks, stored the way submit() stores it (rounded)."""
    from apps.questions import services as qservices

    module = part.module
    a = Attempt.objects.create(
        user=user, part=part, number=number, status=AttemptStatus.SUBMITTED, counted=True,
        all_answered=True, submitted_at=timezone.now(),
        score=policy.percent(D(right), D(total)),
    )  # fmt: skip
    for i in range(total):
        q = qservices.create_question(
            stable_id=f"M{module.number}-R{part.pk}{number}{i:02d}", module=module, pool="module_quiz",
            body={
                "stem": f"Invented {i}?",
                "options": [{"id": f"o{k}", "text": f"Option {k}"} for k in (1, 2, 3, 4)],
                "correct": "o1", "hint": "h", "gate": {},
            },
            tags={"pc": "PC1", "type": "R"},
        )  # fmt: skip
        AttemptItem.objects.create(
            attempt=a,
            position=i + 1,
            question_version=q.current_version,
            points=D(1),
            option_map={},
            score=D(1) if i < right else D(0),
        )
    return a


def test_combined_results_use_unrounded_marks_13_of_15_and_5_of_38(learner):
    part_a, part_b = make_parts([1])[1]
    a = scored_attempt(learner, part_a, 13, 15)
    b = scored_attempt(learner, part_b, 5, 38)
    assert (a.score, b.score) == (D("86.7"), D("13.2"))  # stored for display, rounded
    assert (D("86.7") * 50 + D("13.2") * 50) / 100 == D(
        "49.95"
    )  # the stored values would round up to a pass
    module = compute_results([learner.pk])[learner.pk].modules[0]
    assert module.raw == (50 * (D(100) * 13 / 15) + 50 * (D(100) * 5 / 38)) / 100
    assert module.shown == D("49.9") and not module.passed
    result = compute_results([learner.pk])[learner.pk]
    assert result.modules_shown == D("49.9") and not result.modules_passed and not result.eligible
    assert any("Module 1 is at 49.9%" in x for x in result.blockers)


def test_the_best_attempt_and_the_final_use_unrounded_marks_too(learner):
    part_a, part_b = make_parts([1])[1]
    scored_attempt(learner, part_a, 13, 15, number=1)
    scored_attempt(learner, part_a, 12, 15, number=2)  # 80.0: lower, so 13/15 stays the best
    scored_attempt(learner, part_b, 5, 38)
    r = compute_results([learner.pk])[learner.pk]
    assert r.modules[0].parts[0].best == D(100) * 13 / 15 and r.modules[0].parts[0].best_shown == D(
        "86.7"
    )


def test_pretest_feedback_is_the_overall_score_only_even_when_a_gate_was_triggered(
    learner_client, learner, exam
):
    a, _ = programme.start_programme(learner, "pretest")
    Attempt.objects.filter(pk=a.pk).update(
        status=AttemptStatus.SUBMITTED, score=D("25.0"), counted=False, gate_breached=True,
        all_answered=True, submitted_at=timezone.now(),
    )  # fmt: skip
    html = learner_client.get(reverse("attempt_result", args=[a.pk])).content.decode()
    assert "25.0%" in html and "Pre-test done" in html
    for leak in (
        "Safety gate",
        "doesn&#x27;t count",
        "doesn't count",
        "citizen",
        "Hint",
        "Right",
    ):
        assert leak not in html, leak
    assert not re.search(r">\s*counts\s*<", html)
    intro = learner_client.get(reverse("programme_intro", args=["pretest"])).content.decode()
    assert "25.0%" in intro and "count" not in intro.split("Your attempts")[1]
    assert compute_results([learner.pk])[
        learner.pk
    ].pretest_done  # a gated pre-test still counts as done


# --- review fix: every counted module needs exactly 100 published counted marks ---------------------------


def test_full_marks_on_the_only_50_mark_part_cannot_unlock_the_final(learner):
    parts = make_parts([1])
    AssessmentPart.objects.filter(pk=parts[1][1].pk).delete()  # only the 50-mark Part A is left
    attempt(learner, part=parts[1][0], score="100")
    attempt(learner, kind=ProgrammeAssessmentKind.PRETEST)
    attempt(learner, kind=ProgrammeAssessmentKind.FINAL, score="100")
    r = compute_results([learner.pk])[learner.pk]
    assert r.parts_all_answered and r.pretest_done  # everything the learner can do is done...
    assert not r.final_unlocked and not r.eligible  # ...but the course is not fully set up
    message = "Module 1 has 50 published marks configured; it needs exactly 100."
    assert any(message in b and "Course setup is incomplete" in b for b in r.blockers)
    reasons = programme.final_locked_reasons(learner)
    assert len(reasons) == 1 and message in reasons[0]
    with pytest.raises(programme.Locked, match="50 published marks"):
        programme.start_programme(learner, "final")


def test_marks_over_100_are_also_a_setup_problem_and_exactly_100_is_fine(learner):
    parts = make_parts([1])
    AssessmentPart.objects.filter(pk=parts[1][0].pk).update(marks=60)
    assert any(
        "110 published marks" in g for g in compute_results([learner.pk])[learner.pk].setup_gaps
    )
    AssessmentPart.objects.filter(pk=parts[1][0].pk).update(marks=50)
    assert compute_results([learner.pk])[learner.pk].setup_gaps == []


def test_an_unpublished_counted_part_and_a_marks_gap_are_both_reported(learner):
    parts = make_parts([1])
    AssessmentPart.objects.filter(pk=parts[1][1].pk).update(is_published=False)
    gaps = compute_results([learner.pk])[learner.pk].setup_gaps
    assert any("Part B is not published yet" in g for g in gaps)
    assert any("50 published marks configured" in g for g in gaps)


def test_the_dashboard_shows_which_module_has_how_many_marks(learner_client, learner):
    parts = make_parts([1])
    AssessmentPart.objects.filter(pk=parts[1][1].pk).delete()
    learner.profile.pretest_prompted_at = timezone.now()
    learner.profile.save()
    html = learner_client.get(reverse("start")).content.decode()
    assert "Module 1 has 50 published marks configured" in html
