from typing import ClassVar

from django.db import models


class ImageDecision(models.Model):
    DECISION_KEEP = "keep"
    DECISION_DELETE = "delete"
    DECISIONS: ClassVar = [
        (DECISION_KEEP, "Keep"),
        (DECISION_DELETE, "Delete"),
    ]

    folder = models.CharField(max_length=512)
    filename = models.CharField(max_length=512)
    decision = models.CharField(max_length=10, choices=DECISIONS)
    decided_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("folder", "filename")
        indexes: ClassVar = [
            models.Index(fields=["folder"]),
        ]

    def __str__(self) -> str:
        return f"{self.folder}/{self.filename}: {self.decision}"


class FolderProgress(models.Model):
    folder = models.CharField(max_length=512, unique=True)
    last_classified_name = models.CharField(max_length=512, blank=True, default="")
    last_classified_original = models.CharField(max_length=512, blank=True, default="")
    keep_count = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"{self.folder}: {self.keep_count} keeps (last={self.last_classified_name or '-'})"


# Create your models here.
