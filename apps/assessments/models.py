from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from simple_history.models import HistoricalRecords

from apps.questions.models import Pool


class PartFamily(models.TextChoices):
    MCQ = "mcq", "Multiple choice (part A)"
    INTERACTIVE = "interactive", "Interactive (part B)"


class Selection(models.TextChoices):
    ALL = "all", "All questions, in order"
    ALL_SHUFFLED = "all_shuffled", "All questions, shuffled"
    DRAW = "draw", "A random draw"


class AssessmentPart(models.Model):
    """One graded or practice part of a module, e.g. "Part A: multiple choice" (50 marks)."""

    module = models.ForeignKey("content.Module", on_delete=models.PROTECT, related_name="parts")
    name = models.CharField(max_length=80)
    family = models.CharField(max_length=12, choices=PartFamily.choices, default=PartFamily.MCQ)
    marks = models.PositiveSmallIntegerField(
        default=50
    )  # 0-100; a module's counted parts total 100
    counted = models.BooleanField(default=True)
    selection = models.CharField(max_length=14, choices=Selection.choices, default=Selection.DRAW)
    draw_n = models.PositiveSmallIntegerField(null=True, blank=True)
    min_per_tag = models.PositiveSmallIntegerField(default=0)  # per PC tag in a draw
    pool = models.CharField(max_length=12, choices=Pool.choices, default=Pool.MODULE_QUIZ)
    time_display_minutes = models.PositiveSmallIntegerField(null=True, blank=True)  # null: count-up
    max_attempts = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text="Leave blank for unlimited attempts (D3, D32). Changing it is audited.",
    )
    # Set by publish_part(), which runs validate_part(). Learners can only start published parts.
    is_published = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    history = HistoricalRecords()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["module", "name"], name="uniq_part_name_per_module"),
            models.CheckConstraint(condition=Q(marks__lte=100), name="part_marks_at_most_100"),
            models.CheckConstraint(
                condition=Q(max_attempts__isnull=True) | Q(max_attempts__gte=1),
                name="part_max_attempts_at_least_1",
                violation_error_message="Use at least 1 attempt, or leave blank for unlimited.",
            ),
        ]

    def __str__(self):
        return f"Module {self.module.number} · {self.name}"


class ProgrammeAssessmentKind(models.TextChoices):
    FINAL = "final", _("Final exam")
    PRETEST = "pretest", _("Pre-test")
    MOCK = "mock", _("Practice mock")


class ProgrammeAssessment(models.Model):
    """The final exam and pre-test (built in Stage 5; here so Attempt matches §6)."""

    kind = models.CharField(max_length=10, choices=ProgrammeAssessmentKind.choices, unique=True)
    blueprint = models.JSONField(default=dict, blank=True)
    time_display_minutes = models.PositiveSmallIntegerField(null=True, blank=True)
    cooldown_hours = models.PositiveSmallIntegerField(default=0)
    max_attempts = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text="Final only. Leave blank for unlimited attempts (D3, D32). The pre-test is "
        "always once. Changing it is audited.",
    )

    class Meta:
        constraints = [
            # The pre-test stays once only and the mock is ungraded: only the final takes a limit.
            models.CheckConstraint(
                condition=Q(max_attempts__isnull=True) | (Q(kind="final") & Q(max_attempts__gte=1)),
                name="programme_max_attempts_final_only",
            ),
        ]

    def __str__(self):
        return self.get_kind_display()

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.max_attempts is not None and self.kind != ProgrammeAssessmentKind.FINAL:
            raise ValidationError(
                {"max_attempts": "Only the final takes an attempt limit. The pre-test is once."}
            )
        if self.max_attempts == 0:
            raise ValidationError({"max_attempts": "Use at least 1, or leave blank for unlimited."})


class AttemptStatus(models.TextChoices):
    IN_PROGRESS = "in_progress", "In progress"
    SUBMITTED = "submitted", "Submitted"
    AUTO_SUBMITTED = "auto_submitted", "Auto-submitted"


class Attempt(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="attempts"
    )
    part = models.ForeignKey(
        AssessmentPart, null=True, blank=True, on_delete=models.PROTECT, related_name="attempts"
    )
    programme_assessment = models.ForeignKey(
        ProgrammeAssessment,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="attempts",
    )
    number = models.PositiveIntegerField()
    status = models.CharField(
        max_length=14, choices=AttemptStatus.choices, default=AttemptStatus.IN_PROGRESS
    )
    started_at = models.DateTimeField(auto_now_add=True)
    last_saved_at = models.DateTimeField(auto_now_add=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    score = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)  # percent
    all_answered = models.BooleanField(default=False)
    gate_breached = models.BooleanField(default=False)
    counted = models.BooleanField(default=False)  # submitted AND not gate_breached
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "part", "number"], name="uniq_attempt_number_part"
            ),
            models.UniqueConstraint(
                fields=["user", "programme_assessment", "number"],
                name="uniq_attempt_number_programme",
            ),
            # At most one attempt in progress per learner and part (and per programme assessment).
            models.UniqueConstraint(
                fields=["user", "part"],
                condition=Q(status="in_progress", part__isnull=False),
                name="one_attempt_in_progress_per_part",
            ),
            models.UniqueConstraint(
                fields=["user", "programme_assessment"],
                condition=Q(status="in_progress", programme_assessment__isnull=False),
                name="one_attempt_in_progress_per_programme",
            ),
            models.CheckConstraint(
                condition=Q(part__isnull=False, programme_assessment__isnull=True)
                | Q(part__isnull=True, programme_assessment__isnull=False),
                name="attempt_part_xor_programme",
            ),
        ]
        indexes = [models.Index(fields=["status", "last_saved_at"])]

    def __str__(self):
        return f"Attempt {self.number} of user {self.user_id}"

    @property
    def is_open(self):
        return self.status == AttemptStatus.IN_PROGRESS

    @property
    def title(self):
        """The part's name, or "Final exam" / "Pre-test"."""
        if self.part_id:
            return self.part.name
        return self.programme_assessment.get_kind_display()

    @property
    def module_number(self):
        return self.part.module.number if self.part_id else None


class AttemptItem(models.Model):
    attempt = models.ForeignKey(Attempt, on_delete=models.CASCADE, related_name="items")
    position = models.PositiveIntegerField()  # 1-based
    format = models.CharField(max_length=12, default="mcq")  # frozen with the version
    question_version = models.ForeignKey(
        "questions.QuestionVersion", on_delete=models.PROTECT, related_name="+"
    )
    points = models.DecimalField(max_digits=5, decimal_places=2)  # frozen at draw time
    # {"order": [token, ...], "tokens": {token: internal option id}}: server side only.
    option_map = models.JSONField()
    response = models.JSONField(null=True, blank=True)  # {"choice": token, "flag": bool}
    score = models.DecimalField(max_digits=30, decimal_places=20, null=True, blank=True)  # 0..1
    gate_flag = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["attempt", "position"], name="uniq_item_position"),
            models.CheckConstraint(
                condition=Q(score__isnull=True) | (Q(score__gte=0) & Q(score__lte=1)),
                name="item_score_between_0_and_1",
            ),
        ]
        ordering = ["attempt_id", "position"]

    def __str__(self):
        return f"Item {self.position} of attempt {self.attempt_id}"

    @property
    def answered(self):
        """Complete for its format (an MCQ has a choice; a sort has every item placed; ...)."""
        from apps.questions import formats

        return formats.complete(
            self.format, self.question_version.body, self.option_map, self.response
        )


# --- final exam sets (Stage 5): one set per batch supplies both the pre-test and the final ------


class ExamSetStatus(models.TextChoices):
    DRAFT = "draft", "Draft (not available to learners)"
    RELEASED = "released", "Released"


class ExamSetLocked(Exception):
    """A released exam paper is fixed. Corrections go through a new draft set."""


class ExamSet(models.Model):
    """A fixed final-exam paper, e.g. Set B. Its pre-test questions are a subset of its final."""

    code = models.CharField(max_length=8, unique=True)  # "B", "D"
    name = models.CharField(max_length=80)
    status = models.CharField(
        max_length=10, choices=ExamSetStatus.choices, default=ExamSetStatus.DRAFT
    )
    released_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["code"]

    def __str__(self):
        return f"Set {self.code}" + ("" if self.is_released else " (draft)")

    @property
    def is_released(self):
        return self.status == ExamSetStatus.RELEASED

    def save(self, *args, **kwargs):  # noqa: DJ012
        if self.pk:
            before = ExamSet.objects.filter(pk=self.pk).values("status", "code").first()
            if (
                before
                and before["status"] == ExamSetStatus.RELEASED
                and (self.status != ExamSetStatus.RELEASED or self.code != before["code"])
            ):
                raise ExamSetLocked(f"{self} is released and cannot be changed or withdrawn.")
        super().save(*args, **kwargs)

    def members(self):
        """The items that make up the paper (not those held in reserve or rejected)."""
        return self.items.filter(state=ItemState.MEMBER)


class ItemState(models.TextChoices):
    MEMBER = "member", "In the paper"
    RESERVE = "reserve", "Held in reserve"
    REJECTED = "rejected", "Rejected"


class ExamSetItem(models.Model):
    exam_set = models.ForeignKey(ExamSet, on_delete=models.CASCADE, related_name="items")
    question = models.ForeignKey(
        "questions.Question", on_delete=models.PROTECT, related_name="exam_set_items"
    )
    in_pretest = models.BooleanField(default=False)  # one of the set's shared baseline questions
    state = models.CharField(max_length=10, choices=ItemState.choices, default=ItemState.MEMBER)
    # What release approved: the exact version, marks, format and module. Set once, at release.
    version = models.ForeignKey(
        "questions.QuestionVersion",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    approved_points = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    approved_format = models.CharField(max_length=12, blank=True)
    approved_module = models.ForeignKey(
        "content.Module", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["exam_set", "question"], name="uniq_set_question")
        ]

    def __str__(self):
        return f"{self.exam_set} · {self.question_id}"

    def _check_open(self, set_id):
        if ExamSet.objects.filter(pk=set_id, status=ExamSetStatus.RELEASED).exists():
            raise ExamSetLocked("A released exam set is fixed. Start a new draft set instead.")

    def save(self, *args, **kwargs):  # noqa: DJ012
        self._check_open(self.exam_set_id)
        if self.pk:
            self._check_open(
                ExamSetItem.objects.filter(pk=self.pk).values_list("exam_set_id", flat=True).first()
            )
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        self._check_open(self.exam_set_id)
        return super().delete(*args, **kwargs)


class LearnerExamSet(models.Model):
    """The set and question versions a learner sits, frozen when their first programme exam
    starts. A later batch move or reassignment never changes it, so the pre-test and the final
    always come from the same paper and the shared questions can be compared."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="exam_set_choice"
    )
    exam_set = models.ForeignKey(ExamSet, on_delete=models.PROTECT, related_name="learners")
    # {question_id: question_version_id} for every item of the set, frozen with it
    versions = models.JSONField()
    pretest_question_ids = models.JSONField()
    frozen_at = models.DateTimeField(auto_now_add=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"user {self.user_id} sits {self.exam_set}"
