import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from apps.academics.models import AcademicPeriod, Career, Enrollment


class SupportRuleVersion(models.Model):
    """Immutable published rule version; thresholds are explicit and inspectable."""

    class Indicator(models.TextChoices):
        VERIFIED_AVERAGE_DECLINE = "verified_average_decline", "Descenso del promedio verificado"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    career = models.ForeignKey(Career, on_delete=models.PROTECT, related_name="support_rules")
    valid_from = models.ForeignKey(AcademicPeriod, on_delete=models.PROTECT, related_name="support_rule_versions")
    version = models.PositiveSmallIntegerField()
    indicator = models.CharField(max_length=40, choices=Indicator.choices)
    threshold_points = models.DecimalField(max_digits=5, decimal_places=2, default=10)
    minimum_verified_courses = models.PositiveSmallIntegerField(default=3)
    active = models.BooleanField(default=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="support_rules_created")
    created_at = models.DateTimeField(auto_now_add=True)
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("career__code", "indicator", "-version")
        constraints = [
            models.UniqueConstraint(fields=("career", "indicator", "version"), name="uniq_support_rule_version"),
            models.UniqueConstraint(fields=("career", "indicator"), condition=Q(active=True), name="uniq_active_support_rule"),
        ]

    def clean(self):
        super().clean()
        if self.valid_from_id and self.career_id and self.valid_from.career_id != self.career_id:
            raise ValidationError("La regla y su periodo inicial deben pertenecer a la misma carrera.")
        if self.threshold_points <= 0 or self.threshold_points > 100:
            raise ValidationError({"threshold_points": "El umbral debe estar entre 0 y 100 puntos."})
        if self.minimum_verified_courses < 2:
            raise ValidationError({"minimum_verified_courses": "Se requieren al menos dos asignaturas verificadas por periodo."})

    def save(self, *args, **kwargs):
        if self.pk:
            old = type(self).objects.filter(pk=self.pk).first()
            if old and old.published_at and any(getattr(old, field) != getattr(self, field) for field in (
                "career_id", "valid_from_id", "version", "indicator", "threshold_points", "minimum_verified_courses", "created_by_id", "published_at"
            )):
                raise ValidationError("Una regla activa es inmutable; crea una nueva versión.")
        self.full_clean()
        return super().save(*args, **kwargs)


class SupportAlert(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", "Pendiente de revisión"
        CASE_OPEN = "case_open", "Con acompañamiento"
        RESOLVED = "resolved", "Resuelta"
        DISMISSED = "dismissed", "Descartada"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    rule = models.ForeignKey(SupportRuleVersion, on_delete=models.PROTECT, related_name="alerts")
    enrollment = models.ForeignKey(Enrollment, on_delete=models.PROTECT, related_name="support_alerts")
    period = models.ForeignKey(AcademicPeriod, on_delete=models.PROTECT, related_name="support_alerts")
    evidence_snapshot = models.JSONField()
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.OPEN)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ("-created_at",)
        constraints = [models.UniqueConstraint(fields=("rule", "enrollment", "period"), name="uniq_support_alert_rule_enrollment_period")]

    def clean(self):
        super().clean()
        if self.enrollment_id and self.period_id and (self.enrollment.career_id != self.period.career_id or self.enrollment.period_id != self.period_id):
            raise ValidationError("La alerta, matrícula y periodo deben coincidir.")
        if self.rule_id and self.enrollment_id and self.rule.career_id != self.enrollment.career_id:
            raise ValidationError("La regla no pertenece a la carrera de la matrícula.")


class SupportCase(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", "Abierto"
        IN_PROGRESS = "in_progress", "En seguimiento"
        CLOSED = "closed", "Cerrado"
        DISCARDED = "discarded", "Descartado"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    alert = models.OneToOneField(SupportAlert, on_delete=models.PROTECT, related_name="support_case")
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="support_cases_assigned")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.OPEN)
    outcome = models.CharField(max_length=1000, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="support_cases_created")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)


class SupportAction(models.Model):
    class Kind(models.TextChoices):
        TUTORING = "tutoring", "Tutoría"
        COURSE = "course", "Curso"
        ADVISING = "advising", "Asesoría"
        REINFORCEMENT = "reinforcement", "Refuerzo"
        INTERACTION = "interaction", "Interacción"
        STUDENT_RESPONSE = "student_response", "Respuesta del estudiante"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    case = models.ForeignKey(SupportCase, on_delete=models.PROTECT, related_name="actions")
    kind = models.CharField(max_length=24, choices=Kind.choices)
    description = models.CharField(max_length=1000)
    due_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=(("planned", "Planificada"), ("in_progress", "En curso"), ("completed", "Completada"), ("cancelled", "Cancelada")), default="planned")
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="support_actions_recorded")
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("created_at",)
