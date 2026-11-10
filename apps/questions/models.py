from django.db import models
from simple_history.models import HistoricalRecords


class Format(models.TextChoices):
    """MCQ is built in Stage 2. The 13 interactive formats arrive in Stage 3."""

    MCQ = "mcq", "Multiple choice (part A)"
    MC = "mc", "Interactive: multiple choice"
    SPOT = "spot", "Interactive: spot"
    CHAT = "chat", "Interactive: chat"
    PICK = "pick", "Interactive: pick"
    BUILD = "build", "Interactive: build"
    CROSSWORD = "crossword", "Interactive: crossword"
    SETTINGS = "settings", "Interactive: settings"
    SORT = "sort", "Interactive: sort"
    MATCH = "match", "Interactive: match"
    ORDER = "order", "Interactive: order"
    DIAL = "dial", "Interactive: dial"
    HOTSPOT = "hotspot", "Interactive: hotspot"
    CARDS = "cards", "Interactive: cards"


class Pool(models.TextChoices):
    MODULE_QUIZ = "module_quiz", "Module quiz"
    FINAL = "final", "Final exam"
    PRACTICE = "practice", "Practice"


class QuestionStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    LIVE = "live", "Live"
    RETIRED = "retired", "Retired"


class PoolLocked(Exception):
    pass


class Question(models.Model):
    stable_id = models.CharField(max_length=30, unique=True)  # e.g. M4-12
    module = models.ForeignKey("content.Module", on_delete=models.PROTECT, related_name="questions")
    format = models.CharField(max_length=12, choices=Format.choices, default=Format.MCQ)
    tags = models.JSONField(default=dict, blank=True)  # {"pc": "PC3", "type": "A"}
    pool = models.CharField(max_length=12, choices=Pool.choices)
    is_anchor = models.BooleanField(default=False)
    points = models.DecimalField(max_digits=5, decimal_places=2, default=1)
    status = models.CharField(
        max_length=10, choices=QuestionStatus.choices, default=QuestionStatus.DRAFT
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    history = HistoricalRecords()

    class Meta:
        ordering = ["stable_id"]
        indexes = [models.Index(fields=["module", "pool", "status"])]

    def __str__(self):
        return self.stable_id

    def save(self, *args, **kwargs):
        if self.pk and self.pool == Pool.FINAL:
            before = Question.objects.filter(pk=self.pk).values_list("pool", flat=True).first()
            if before and before != Pool.FINAL and self.shown_in_non_final_attempt():
                raise PoolLocked(
                    f"{self.stable_id} has been shown in a non-final attempt, so it cannot move "
                    "into the final pool. Write a new question for the final."
                )
        super().save(*args, **kwargs)

    @property
    def current_version(self):
        return self.versions.order_by("-version").first()

    def shown_in_non_final_attempt(self) -> bool:
        """True if any learner has already been shown this question outside the final exam."""
        from apps.assessments.models import AttemptItem

        return (
            AttemptItem.objects.filter(question_version__question=self)
            .exclude(attempt__programme_assessment__kind="final")
            .exists()
        )


class QuestionVersion(models.Model):
    """One immutable version of a question's content (D11, CLAUDE.md "Never").

    A change makes a new version. Besides this guard, a database trigger refuses UPDATE and
    DELETE, so not even a script or the admin can edit a version in place.
    """

    question = models.ForeignKey(Question, on_delete=models.PROTECT, related_name="versions")
    version = models.PositiveIntegerField()
    body = models.JSONField()  # validated by apps.questions.schemas for the question's format
    content_hash = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["question", "version"], name="uniq_question_version")
        ]
        ordering = ["question_id", "version"]

    def __str__(self):
        return f"{self.question.stable_id} v{self.version}"

    def save(self, *args, **kwargs):
        if self.pk:
            raise RuntimeError("A QuestionVersion is never edited: add a new version instead.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise RuntimeError("A QuestionVersion is never deleted.")


class QuestionImage(models.Model):
    """A picture for a hotspot question: an uploaded raster image, validated and re-encoded.

    Content is never raw SVG or HTML (CLAUDE.md "Never"): the picture is a PNG, JPEG or WebP made
    by apps/questions/images.py (metadata stripped, size limited), and the tappable regions are a
    list of shapes in the question body, drawn by our own renderer.
    """

    file = models.FileField(upload_to="question-images/")
    sha256 = models.CharField(max_length=64, unique=True)
    format = models.CharField(max_length=5)  # png / jpeg / webp
    width = models.PositiveIntegerField()
    height = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Image {self.pk} ({self.width}x{self.height} {self.format})"
