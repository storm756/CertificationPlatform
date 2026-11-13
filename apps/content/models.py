"""Learning content (architecture §6 Content, §8, §13.1).

A Module holds Units (film, reading topic, handout, practice check, practice quiz). A Unit's text
lives in UnitVersion rows: blocks validated by apps/content/blocks.py, never raw HTML. A version's
title and blocks never change once written (a model guard and a database trigger); an edit is a new
version. One version per unit is published at a time.
"""

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.db.models import Q


class ModuleKind(models.TextChoices):
    LEARNING = "learning", "Learning module"
    CAPSTONE = "capstone", "Capstone"


class Module(models.Model):
    number = models.PositiveSmallIntegerField(unique=True)
    slug = models.SlugField(unique=True)
    title_key = models.CharField(max_length=80)  # translation key (Stage 8)
    title = models.CharField(max_length=200, blank=True)  # English; translations come in Stage 8
    tagline = models.CharField(max_length=300, blank=True)
    hours = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    theory_hours = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    practical_hours = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    # The module page's overview: what it is, outcomes, key rule, stop/save/report. Validated by
    # blocks.ModuleOverview. Plain text only.
    overview = models.JSONField(default=dict, blank=True)
    kind = models.CharField(max_length=10, choices=ModuleKind.choices, default=ModuleKind.LEARNING)
    counted = models.BooleanField(
        default=True
    )  # the capstone is a learning module, not graded (D26)
    order = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["order", "number"]

    def __str__(self):
        return f"Module {self.number}"

    @property
    def display_title(self):
        return self.title or f"Module {self.number}"


class UnitType(models.TextChoices):
    VIDEO = "video", _("Film")
    READING = "reading", _("Reading topic")
    HANDOUT = "handout", _("Handout")
    CHECK = "check", _("Practice check")
    PRACTICE_QUIZ = "practice_quiz", _("Practice quiz")


class Unit(models.Model):
    module = models.ForeignKey(Module, on_delete=models.PROTECT, related_name="units")
    slug = models.SlugField(
        max_length=40
    )  # stable within the module: film, t1 … t7, handout, check
    type = models.CharField(max_length=16, choices=UnitType.choices)
    order = models.PositiveSmallIntegerField(default=0)
    nominal_minutes = models.PositiveSmallIntegerField(default=10)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["module__order", "order", "pk"]
        constraints = [
            models.UniqueConstraint(fields=["module", "slug"], name="content_unit_slug_per_module")
        ]
        permissions = [("publish_unit", "Content publisher: publish and restore unit versions")]

    def __str__(self):
        return f"Module {self.module.number} · {self.slug}"

    def published(self):
        return self.versions.filter(status=VersionStatus.PUBLISHED).first()


class VersionStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    PUBLISHED = "published", "Published"
    SUPERSEDED = "superseded", "Superseded"


class VersionSource(models.TextChoices):
    LEGACY = "legacy", "Legacy import"
    DOCX = "docx", "Word upload"
    EDITOR = "editor", "Editor"
    RESTORE = "restore", "Restored"


class ImmutableVersion(Exception):
    pass


class UnitVersion(models.Model):
    unit = models.ForeignKey(Unit, on_delete=models.PROTECT, related_name="versions")
    version = models.PositiveIntegerField()
    title = models.CharField(max_length=200)
    blocks = models.JSONField(default=list)
    status = models.CharField(
        max_length=12, choices=VersionStatus.choices, default=VersionStatus.DRAFT
    )
    source = models.CharField(max_length=10, choices=VersionSource.choices)
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    published_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    published_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["unit", "-version"]
        constraints = [
            models.UniqueConstraint(fields=["unit", "version"], name="content_version_unique"),
            models.UniqueConstraint(
                fields=["unit"],
                condition=Q(status="published"),
                name="content_one_published_version",
            ),
        ]

    def __str__(self):
        return f"{self.unit} v{self.version} ({self.status})"

    def save(self, *args, **kwargs):
        if self.pk:
            before = (
                UnitVersion.objects.filter(pk=self.pk).values("title", "blocks", "unit_id").first()
            )
            if before and (
                before["title"] != self.title
                or before["blocks"] != self.blocks
                or before["unit_id"] != self.unit_id
            ):
                raise ImmutableVersion("A unit version's text never changes: add a new version.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ImmutableVersion("Unit versions are kept as history.")


class MediaKind(models.TextChoices):
    PDF = "pdf", "PDF handout"
    IMAGE = "image", "Image"
    POSTER = "poster", "Film poster"
    CAPTION = "caption", "Caption file"
    MP4 = "mp4", "MP4 film"


class MediaAsset(models.Model):
    module = models.ForeignKey(Module, on_delete=models.PROTECT, related_name="media")
    kind = models.CharField(max_length=10, choices=MediaKind.choices)
    language = models.CharField(max_length=5, default="en")
    title = models.CharField(max_length=200, blank=True)
    file = models.FileField(upload_to="content/")
    content_type = models.CharField(max_length=60)
    sha256 = models.CharField(max_length=64, db_index=True)
    size = models.PositiveBigIntegerField()
    width = models.PositiveIntegerField(null=True, blank=True)
    height = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.get_kind_display()} · module {self.module.number} · {self.title or self.pk}"


class UnitProgress(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    unit = models.ForeignKey(Unit, on_delete=models.CASCADE, related_name="progress")
    completed_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "unit"], name="content_progress_once")
        ]

    def __str__(self):
        return f"{self.user_id} completed {self.unit_id}"


class TimeLog(models.Model):
    """Engaged time (estimated), adults only (D16). One row per user, unit and day."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    unit = models.ForeignKey(Unit, on_delete=models.CASCADE, related_name="+")
    date = models.DateField()
    seconds = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "unit", "date"], name="content_timelog_day")
        ]

    def __str__(self):
        return f"{self.user_id} {self.unit_id} {self.date}"


class LearnCheck(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    question_version = models.ForeignKey(
        "questions.QuestionVersion", on_delete=models.PROTECT, related_name="+"
    )
    unit = models.ForeignKey(Unit, null=True, on_delete=models.SET_NULL, related_name="+")
    score = models.DecimalField(max_digits=30, decimal_places=20)
    at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user_id} {self.question_version_id} {self.score}"
