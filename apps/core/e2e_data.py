"""Invented data for the browser journeys (`e2e/`) and the load test (`loadtest/`).

Used only by `manage.py e2e_seed`, `e2e_clean` and `loadtest_seed`. Everything here is made up:
no real person, question or answer. Every row carries a marker so that the clean commands remove
exactly what was added and nothing else:

* e-mail addresses end in `@e2e.example.com` (journeys) or `@load.example.com` (load test);
* batch codes start with `E2E-` or `LT-`; the exam set is `E2EJ`; part names start with `E2E-J`;
  question ids start with `E2EJ-`; the sandbox module is number 91.

The seed never edits an existing batch, learner, question, part or module, and it refuses to run on
production (`guard()`). The browser only ever sees what the real pages send: the invented
questions say in their own wording which option is right, so a test can answer without a key.
"""

import os
from datetime import date, timedelta

from allauth.account.models import EmailAddress
from allauth.mfa.models import Authenticator
from django.core.management.base import CommandError
from django.db import DatabaseError, connection, transaction
from django.utils import timezone

from apps.accounts.models import Profile, Role, User
from apps.assessments import examsets, programme, rules
from apps.assessments.models import (
    AssessmentPart,
    Attempt,
    AttemptStatus,
    ExamSet,
    ExamSetItem,
    PartFamily,
    ProgrammeAssessmentKind,
    Selection,
)
from apps.batches.models import Batch, BatchMentor, Enrolment
from apps.content.models import Module, ModuleKind
from apps.questions import legacy_interactive, schemas
from apps.questions import services as qservices
from apps.questions.models import Pool, Question, QuestionVersion

JOURNEY_DOMAIN = "e2e.example.com"
LOAD_DOMAIN = "load.example.com"
PASSWORD = "e2e-Invented-Pass-42"  # invented; only ever valid for the marked test accounts  # noqa: S105
TOTP_SECRET = "JBSWY3DPEHPK3PXP"  # invented; staff test accounts use it (e2e/support/totp.ts)  # noqa: S105
EXAM_SET_CODE = "E2EJ"
SANDBOX_MODULE = 91
PART_PREFIX = "E2E-J"
QUESTION_PREFIX = "E2EJ-"
RIGHT, WRONG = "The RIGHT answer to {n}", "A WRONG answer {k} to {n}"

# Journey learners: (key, batch code, name, preferred language, state)
#   state: "fresh" (nothing done), "locked" (17 of 18 parts answered, one submitted with blanks),
#   "ready" (every part answered and the pre-test done: the final is open)
LEARNERS = [
    ("fresh", "E2E-B01", "Fresh Learner", "en", "fresh"),
    ("work", "E2E-B01", "Practice Learner", "en", "fresh"),
    ("locked", "E2E-B01", "Locked Learner", "en", "locked"),
    ("final", "E2E-B01", "Final Learner", "en", "ready"),
    ("marathi", "E2E-B01", "Marathi Learner", "mr", "ready"),
    ("cert", "E2E-B02", "Certificate Learner", "en", "ready"),
    ("race", "E2E-B02", "Race Learner", "en", "ready"),
    ("other", "E2E-B02", "Other Learner", "en", "fresh"),
]
BATCHES = [
    # code, name, accepting, auto_issue
    ("E2E-B01", "E2E batch one", False, False),
    ("E2E-B02", "E2E batch two", False, True),
    ("E2E-B03", "E2E batch three", True, False),
]
STAFF = [
    # key, role, batches the mentor looks after
    ("mentor1", Role.MENTOR, ["E2E-B01", "E2E-B03"]),
    ("mentor2", Role.MENTOR, ["E2E-B02"]),
    ("admin", Role.ADMIN, []),
]


def guard():
    """Refuse to run anywhere but development and staging."""
    module = os.environ.get("DJANGO_SETTINGS_MODULE", "")
    if not (module.endswith(".dev") or module.endswith(".staging")):
        raise CommandError(
            f"Refusing to run with settings '{module}'. Seeding is for dev and staging only."
        )


def email(key, domain=JOURNEY_DOMAIN):
    return f"{key}@{domain}"


# --- people -------------------------------------------------------------------------------------


def _user(key, role, batch=None, name=None, language="en", domain=JOURNEY_DOMAIN):
    address = email(key, domain)
    user = User.objects.filter(email=address).first()
    if user is not None:
        return user
    if role == Role.ADMIN:
        user = User.objects.create_superuser(address, PASSWORD)
    else:
        user = User.objects.create_user(address, PASSWORD, role=role, is_staff=False)
    EmailAddress.objects.create(user=user, email=address, primary=True, verified=True)
    Profile.objects.create(
        user=user,
        certificate_name=name or "E2E Staff",
        date_of_birth=date(1990, 1, 1) if role != Role.LEARNER else date(2000, 1, 1),
        preferred_language=language,
    )
    if batch is not None:
        Enrolment.objects.create(user=user, batch=batch)
    if role != Role.LEARNER:
        Authenticator.objects.create(
            user=user, type=Authenticator.Type.TOTP, data={"secret": TOTP_SECRET}
        )
    return user


# --- the course ---------------------------------------------------------------------------------


def _mcq_body(n, hint="E2E hint."):
    options = [
        {"id": "o1", "text": WRONG.format(k=1, n=n)},
        {"id": "o2", "text": RIGHT.format(n=n)},
        {"id": "o3", "text": WRONG.format(k=2, n=n)},
        {"id": "o4", "text": WRONG.format(k=3, n=n)},
    ]
    return {
        "stem": f"E2E question {n}: choose the option that says RIGHT.",
        "options": options,
        "correct": "o2",  # never first, so a position-based guess is wrong
        "hint": hint,
        "gate": {},
    }


def _question(stable_id, module, n, pool, tags=None, **extra):
    question = Question.objects.filter(stable_id=stable_id).first()
    if question is None:
        question = qservices.create_question(
            stable_id=stable_id,
            module=module,
            body=extra.pop("body", None) or _mcq_body(n),
            tags=tags if tags is not None else {"pc": "PC1", "type": "R"},
            pool=pool,
            **extra,
        )
        qservices.publish(question)
    return question


def _part(module, name, *, family=PartFamily.MCQ, marks=0, counted=False, published=True):
    part = AssessmentPart.objects.filter(module=module, name=name).first()
    if part is None:
        part = AssessmentPart.objects.create(
            module=module,
            name=name,
            family=family,
            marks=marks,
            counted=counted,
            selection=Selection.ALL,
        )
        if published:
            rules.publish_part(part)
    return part


def ensure_module(number, **defaults):
    module, _ = Module.objects.get_or_create(
        number=number,
        defaults={
            "slug": f"module-{number}",
            "title_key": f"module.{number}.title",
            "order": number,
        }
        | defaults,
    )
    return module


def ensure_course():
    """The pieces the journeys need. Returns {"sandbox_mcq", "sandbox_gate", "extra", "parts"}.

    * A sandbox module (91, not counted) with an invented multiple-choice part and an invented
      interactive part that has a gate option. Nothing in the real course is touched.
    * If a counted module has no published counted part (an empty database, as in CI), one
      invented part of 100 marks, so the course is complete. A real course is left alone.
    * One uncounted extra part in module 1 for the "make a new part counted" journey.
    """
    for number in range(1, 10):  # the counted learning modules (a migration seeds them)
        ensure_module(number)
    sandbox = ensure_module(
        SANDBOX_MODULE,
        slug="e2e-sandbox",
        title="E2E sandbox",
        kind=ModuleKind.CAPSTONE,
        counted=False,
    )
    for n in range(1, 6):
        _question(f"{QUESTION_PREFIX}S-{n:02d}", sandbox, n, Pool.MODULE_QUIZ)
    sandbox_mcq = _part(sandbox, f"{PART_PREFIX} multiple choice")

    gate_id = f"{QUESTION_PREFIX}GATE-01"
    if not Question.objects.filter(stable_id=gate_id).exists():
        fmt, body = legacy_interactive.convert(
            {
                "type": "mc",
                "title": "E2E gate check",
                "ask": "A stranger asks for your one-time code. What do you do?",
                "opts": [
                    {"t": "Say no and tell your mentor"},
                    {"t": "Share the code"},
                    {"t": "Ignore the message"},
                ],
                "a": 0,
                "why": "Never share a one-time code.",
            }
        )
        body["options"][1]["gate"] = True
        body["gate_message"] = "E2E: sharing the code would put someone at risk."
        body["hint"] = "E2E gate hint."
        body = schemas.parse_body(fmt, body).model_dump()
        question = qservices.create_question(
            stable_id=gate_id, module=sandbox, fmt=fmt, body=body, tags={}, pool=Pool.MODULE_QUIZ
        )
        qservices.publish(question)
    sandbox_gate = _part(sandbox, f"{PART_PREFIX} interactive gate", family=PartFamily.INTERACTIVE)

    parts = []
    for module in Module.objects.filter(kind=ModuleKind.LEARNING, counted=True):
        counted = [
            p
            for p in AssessmentPart.objects.filter(module=module, counted=True, is_published=True)
            if not p.name.startswith(PART_PREFIX)
        ]
        if not counted:  # an empty course (CI): one invented part carrying all 100 marks
            for n in range(1, 4):
                _question(f"{QUESTION_PREFIX}M{module.number}-{n:02d}", module, n, Pool.MODULE_QUIZ)
            counted = [
                _part(module, f"{PART_PREFIX} part {module.number}", marks=100, counted=True)
            ]
        parts.extend(counted)
    module1 = Module.objects.get(number=1)
    extra = _part(module1, f"{PART_PREFIX} extra part", marks=10, counted=False, published=False)
    if not extra.is_published:  # published directly: it has no questions of its own
        extra.is_published = True
        extra.save(update_fields=["is_published"])
    return {
        "sandbox_mcq": sandbox_mcq,
        "sandbox_gate": sandbox_gate,
        "extra": extra,
        "parts": parts,
    }


def ensure_exam_set(admin):
    """A released exam set (code E2EJ) that matches the final's blueprint, and its questions."""
    exam_set = ExamSet.objects.filter(code=EXAM_SET_CODE).first()
    if exam_set is not None and exam_set.is_released:
        return exam_set
    with transaction.atomic():
        exam_set = examsets.lock_set(EXAM_SET_CODE, "E2E journeys set", create=True)
        for number, count in sorted(programme.final_blueprint().items()):
            module = Module.objects.get(number=number)
            for k in range(1, count + 1):
                question = _question(
                    f"{QUESTION_PREFIX}F-{number}-{k:02d}",
                    module,
                    1000 * number + k,
                    Pool.FINAL,
                )
                ExamSetItem.objects.get_or_create(
                    exam_set=exam_set, question=question, defaults={"in_pretest": k <= 2}
                )
        errors = examsets.release(exam_set, admin)
    if errors:
        raise CommandError("The E2E exam set could not be released: " + "; ".join(errors))
    return exam_set


# --- learners' progress -------------------------------------------------------------------------


def _submitted(user, *, part=None, kind=None, score=80, all_answered=True, number=1, when=None):
    """A finished attempt with no items: results fall back to the stored score (policy.py)."""
    assessment = programme.get_assessment(kind) if kind else None
    return Attempt.objects.create(
        user=user,
        part=part,
        programme_assessment=assessment,
        number=number,
        status=AttemptStatus.SUBMITTED,
        score=score,
        all_answered=all_answered,
        counted=True,
        submitted_at=when or timezone.now() - timedelta(days=1),
    )


def finish_course(user, parts, *, leave_blank=False):
    """Mark every counted part as submitted at 80%. With leave_blank, the last one was submitted
    with blanks, so it is not 'answered' and the final stays locked."""
    for index, part in enumerate(parts):
        blank = leave_blank and index == len(parts) - 1
        _submitted(user, part=part, all_answered=not blank, score=40 if blank else 80)


def finish_pretest(user):
    _submitted(user, kind=ProgrammeAssessmentKind.PRETEST, score=40)


# --- the journey seed ---------------------------------------------------------------------------


def seed_journeys():
    """Create (or complete) the journey data and return the manifest the tests read."""
    guard()
    admin = _user("admin", Role.ADMIN)
    course = ensure_course()
    exam_set = ensure_exam_set(admin)
    batches = {}
    for code, name, accepting, auto_issue in BATCHES:
        batch, created = Batch.objects.get_or_create(
            code=code,
            defaults={
                "name": name,
                "accepting": accepting,
                "auto_issue": auto_issue,
                "seat_limit": 500,
                "centre": "E2E centre",
                "centre_code": "E2E",
            },
        )
        if exam_set.is_released and batch.exam_set_id is None:
            examsets.assign(batch, exam_set, admin)
        batches[code] = batch
    staff = {}
    for key, role, mentored in STAFF:
        user = _user(key, role)
        for code in mentored:
            BatchMentor.objects.get_or_create(batch=batches[code], mentor=user)
        staff[key] = user
    learners = {}
    for key, code, name, language, state in LEARNERS:
        existing = User.objects.filter(email=email(key)).exists()
        user = _user(key, Role.LEARNER, batches[code], name, language)
        if not existing and state in ("locked", "ready"):
            finish_course(user, course["parts"], leave_blank=state == "locked")
            if state == "ready":
                finish_pretest(user)
        learners[key] = user
    final_question = Question.objects.filter(
        pool=Pool.FINAL, stable_id__startswith=QUESTION_PREFIX
    ).first()
    return {
        "password": PASSWORD,
        "totp_secret": TOTP_SECRET,
        "domain": JOURNEY_DOMAIN,
        "batches": {code: b.pk for code, b in batches.items()},
        "users": {key: u.email for key, u in {**staff, **learners}.items()},
        "learner_ids": {key: u.pk for key, u in learners.items()},
        "parts": {
            "mcq": course["sandbox_mcq"].pk,
            "gate": course["sandbox_gate"].pk,
            "extra": course["extra"].pk,
        },
        "final_question_id": final_question.pk if final_question else None,
        "exam_set": exam_set.code,
    }


# --- clean --------------------------------------------------------------------------------------


def clean_marked(domains, batch_prefixes):
    """Remove everything the seeds added (and the learners and certificates journeys created for
    marked accounts). Returns a {what: count} summary. Order matters: rows that protect others
    (certificates, attempts, enrolments, exam-set links) go first."""
    from apps.certificates.models import Certificate

    guard()
    done = {}
    users = User.objects.none()
    for domain in domains:
        users = users | User.objects.filter(email__iendswith="@" + domain)
    user_ids = list(users.values_list("pk", flat=True))
    done["certificates"] = Certificate.objects.filter(user_id__in=user_ids).delete()[0]
    done["attempts"] = Attempt.objects.filter(user_id__in=user_ids).delete()[0]
    done["users"] = User.objects.filter(pk__in=user_ids).delete()[0]
    batches = Batch.objects.none()
    for prefix in batch_prefixes:
        batches = batches | Batch.objects.filter(code__startswith=prefix)
    done["batches"] = batches.delete()[0]
    return done


# Released papers and question versions are fixed by database triggers (D31, D5). Removing the
# invented ones means switching those triggers off for one transaction, which only the table owner
# (the development database) may do. On staging the app's role cannot, so the invented set and
# questions are left in place (inert, marked E2EJ, used by no real batch) and the command says so.
GUARDED_TABLES = (
    "assessments_examset",
    "assessments_examsetitem",
    "questions_question",
    "questions_questionversion",
)


def _triggers(state):
    with connection.cursor() as cursor:
        for table in GUARDED_TABLES:
            cursor.execute(f"ALTER TABLE {table} {state} TRIGGER USER")


def clean_course():
    """Remove the invented parts, questions, exam set and the sandbox module."""
    guard()
    done = {}
    with transaction.atomic():
        done["parts"] = AssessmentPart.objects.filter(name__startswith=PART_PREFIX).delete()[0]
    try:
        with transaction.atomic():
            _triggers("DISABLE")  # first, before any delete queues trigger events
            done["exam_set"] = ExamSet.objects.filter(code=EXAM_SET_CODE).delete()[0]
            questions = Question.objects.filter(stable_id__startswith=QUESTION_PREFIX)
            QuestionVersion.objects.filter(question__in=questions).delete()  # versions protect them
            done["questions"] = questions.delete()[0]
            done["modules"] = Module.objects.filter(number=SANDBOX_MODULE).delete()[0]
            connection.cursor().execute("SET CONSTRAINTS ALL IMMEDIATE")
            _triggers("ENABLE")
    except DatabaseError as exc:
        done["kept"] = (
            "exam set E2EJ, its questions and module 91 stay: this database role may not "
            f"switch off the fixed-paper triggers ({type(exc).__name__})"
        )
    return done


# --- the load test ------------------------------------------------------------------------------

LOAD_BATCH = "LT-01"


def seed_load(count=60):
    """`count` invented learners (lt001@load.example.com …) with the final open, in one batch."""
    guard()
    admin = _user("lt-admin", Role.ADMIN, domain=LOAD_DOMAIN)
    course = ensure_course()
    exam_set = ensure_exam_set(admin)
    batch, _ = Batch.objects.get_or_create(
        code=LOAD_BATCH,
        defaults={"name": "Load test batch", "seat_limit": count + 100, "centre_code": "LOAD"},
    )
    if batch.exam_set_id is None:
        examsets.assign(batch, exam_set, admin)
    made = 0
    for n in range(1, count + 1):
        key = f"lt{n:03d}"
        if User.objects.filter(email=email(key, LOAD_DOMAIN)).exists():
            continue
        user = _user(key, Role.LEARNER, batch, f"Load Learner {_word(n)}", domain=LOAD_DOMAIN)
        finish_course(user, course["parts"])
        finish_pretest(user)
        made += 1
    return {
        "count": count,
        "created": made,
        "password": PASSWORD,
        "email_pattern": f"lt{{n:03d}}@{LOAD_DOMAIN}",
        "batch": LOAD_BATCH,
    }


def _word(n):
    """Certificate names are English letters only (D37): 1 -> 'A', 27 -> 'AA'."""
    out = ""
    while n:
        n, r = divmod(n - 1, 26)
        out = chr(65 + r) + out
    return out
