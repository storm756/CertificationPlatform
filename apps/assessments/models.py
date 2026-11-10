from django.conf import settings
from django.db import models
from django.db.models import Q

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
    # Set by publish_part(), which runs validate_part(). Learners can only start published parts.
    is_published = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["module", "name"], name="uniq_part_name_per_module"),
            models.CheckConstraint(condition=Q(marks__lte=100), name="part_marks_at_most_100"),
        ]

    def __str__(self):
        return f"Module {self.module.number} · {self.name}"


class ProgrammeAssessmentKind(models.TextChoices):
    FINAL = "final", "Final exam"
    PRETEST = "pretest", "Pre-test"
    MOCK = "mock", "Practice mock"


class ProgrammeAssessment(models.Model):
    """The final exam and pre-test (built in Stage 5; here so Attempt matches §6)."""

    kind = models.CharField(max_length=10, choices=ProgrammeAssessmentKind.choices, unique=True)
    blueprint = models.JSONField(default=dict, blank=True)
    time_display_minutes = models.PositiveSmallIntegerField(null=True, blank=True)
    cooldown_hours = models.PositiveSmallIntegerField(default=0)

    def __str__(self):
        return self.get_kind_display()


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
