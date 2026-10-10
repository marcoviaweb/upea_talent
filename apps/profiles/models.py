import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.academics.models import Enrollment


class DevelopmentRecord(models.Model):
    class Status(models.TextChoices):
        DECLARED = "declared", "Declarado"
        IN_REVIEW = "in_review", "En revisión"
        VALIDATED = "validated", "Validado"
        NEEDS_CHANGES = "needs_changes", "Requiere cambios"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    enrollment = models.ForeignKey(Enrollment, on_delete=models.PROTECT, related_name="%(class)ss")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DECLARED)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="%(class)ss_created")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    validated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="%(class)ss_validated")
    validated_at = models.DateTimeField(null=True, blank=True)
    review_note = models.CharField(max_length=500, blank=True)

    class Meta:
        abstract = True
        ordering = ("-created_at",)

    def clean(self):
        super().clean()
        if self.status == self.Status.VALIDATED and (not self.validated_by_id or not self.validated_at):
            raise ValidationError("Un registro validado debe identificar a quien lo validó y cuándo.")
        if self.status != self.Status.VALIDATED and (self.validated_by_id or self.validated_at):
            raise ValidationError("Solo los registros validados pueden tener datos de validación.")


class StudentProject(DevelopmentRecord):
    title = models.CharField(max_length=160)
    description = models.TextField(max_length=3000)
    role = models.CharField("participación", max_length=120)
    started_on = models.DateField(null=True, blank=True)
    completed_on = models.DateField(null=True, blank=True)

    class Meta(DevelopmentRecord.Meta):
        verbose_name = "proyecto estudiantil"
        verbose_name_plural = "proyectos estudiantiles"

    def clean(self):
        super().clean()
        if self.started_on and self.completed_on and self.completed_on < self.started_on:
            raise ValidationError({"completed_on": "La fecha de finalización debe ser posterior al inicio."})

    def __str__(self):
        return self.title


class StudentSkill(DevelopmentRecord):
    name = models.CharField("habilidad", max_length=100)
    proficiency_label = models.CharField("nivel declarado", max_length=40, blank=True)
    description = models.CharField(max_length=500, blank=True)

    class Meta(DevelopmentRecord.Meta):
        verbose_name = "habilidad estudiantil"
        verbose_name_plural = "habilidades estudiantiles"

    def __str__(self):
        return self.name
