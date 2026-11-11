from django.db import models


class ModuleKind(models.TextChoices):
    LEARNING = "learning", "Learning module"
    CAPSTONE = "capstone", "Capstone"


class Module(models.Model):
    """A course module. Stage 2 only needs the identity; Stage 4 adds units and content."""

    number = models.PositiveSmallIntegerField(unique=True)
    slug = models.SlugField(unique=True)
    title_key = models.CharField(max_length=80)  # translation key; the text comes in Stage 4/8
    hours = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
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
