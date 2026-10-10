import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from apps.academics.models import AcademicPeriod, Career, CourseOffering, Enrollment, TeachingAssignment


class EvaluationCampaign(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Borrador"
        OPEN = "open", "Abierta"
        CLOSED = "closed", "Cerrada"
        PUBLISHED = "published", "Resultados publicados"
        CANCELLED = "cancelled", "Cancelada"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    career = models.ForeignKey(Career, on_delete=models.PROTECT, related_name="evaluation_campaigns")
    period = models.ForeignKey(AcademicPeriod, on_delete=models.PROTECT, related_name="evaluation_campaigns")
    offering = models.ForeignKey(CourseOffering, on_delete=models.PROTECT, related_name="evaluation_campaigns")
    title = models.CharField(max_length=180)
    version = models.PositiveSmallIntegerField(default=1)
    questionnaire_version = models.CharField(max_length=24, default="UPEA-STRUCTURED-1")
    minimum_responses = models.PositiveSmallIntegerField(default=5)
    opens_at = models.DateTimeField()
    closes_at = models.DateTimeField()
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="evaluation_campaigns_created")
    supersedes = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT, related_name="successors")
    published_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    results_published_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(fields=("offering", "version"), name="uniq_evaluation_offering_version"),
            models.CheckConstraint(condition=Q(minimum_responses__gte=5), name="evaluation_minimum_five"),
            models.CheckConstraint(condition=Q(closes_at__gt=models.F("opens_at")), name="evaluation_campaign_dates_ordered"),
        ]

    def clean(self):
        super().clean()
        if self.offering_id and self.career_id and self.period_id:
            if self.offering.course.career_id != self.career_id or self.offering.period_id != self.period_id:
                raise ValidationError("La campaña, carrera, periodo y grupo deben coincidir.")
        if self.minimum_responses and self.minimum_responses < 5:
            raise ValidationError({"minimum_responses": "El mínimo de privacidad no puede ser menor a cinco."})

    def save(self, *args, **kwargs):
        if self.pk and type(self).objects.filter(pk=self.pk, status__in=(self.Status.OPEN, self.Status.CLOSED, self.Status.PUBLISHED)).exists():
            previous = type(self).objects.get(pk=self.pk)
            protected = ("career_id", "period_id", "offering_id", "title", "version", "questionnaire_version", "minimum_responses", "opens_at", "closes_at", "created_by_id")
            if any(getattr(previous, field) != getattr(self, field) for field in protected):
                raise ValidationError("Una campaña publicada es inmutable; crea una versión nueva antes de recibir respuestas.")
        return super().save(*args, **kwargs)


class EvaluationTarget(models.Model):
    """The person/assignment being evaluated, snapshotted at campaign publication."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    campaign = models.ForeignKey(EvaluationCampaign, on_delete=models.PROTECT, related_name="targets")
    assignment = models.ForeignKey(TeachingAssignment, on_delete=models.PROTECT, related_name="evaluation_targets")
    subject = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="evaluation_targets")
    subject_role = models.CharField(max_length=12, choices=TeachingAssignment.AssignmentRole.choices)
    subject_name = models.CharField(max_length=180)

    class Meta:
        ordering = ("subject_role", "subject_name")
        constraints = [models.UniqueConstraint(fields=("campaign", "assignment"), name="uniq_evaluation_target_assignment")]


class EvaluationEligibility(models.Model):
    """Identity-bearing ballot entitlement; never exposed to the evaluated subject."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    campaign = models.ForeignKey(EvaluationCampaign, on_delete=models.PROTECT, related_name="eligibilities")
    target = models.ForeignKey(EvaluationTarget, on_delete=models.PROTECT, related_name="eligibilities")
    enrollment = models.ForeignKey(Enrollment, on_delete=models.PROTECT, related_name="evaluation_eligibilities")
    answered = models.BooleanField(default=False)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("target", "enrollment"), name="uniq_evaluation_voter_target")]
        indexes = [models.Index(fields=("enrollment", "campaign"), name="evaluation_eligibility_lookup")]

    def clean(self):
        super().clean()
        if self.target_id and self.campaign_id and self.target.campaign_id != self.campaign_id:
            raise ValidationError("La elegibilidad y el objetivo deben pertenecer a la misma campaña.")


class EvaluationSubmission(models.Model):
    """Anonymous structured ballot: deliberately has no FK to user/enrollment/eligibility."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    campaign = models.ForeignKey(EvaluationCampaign, on_delete=models.PROTECT, related_name="submissions")
    target = models.ForeignKey(EvaluationTarget, on_delete=models.PROTECT, related_name="submissions")
    response = models.JSONField()
    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("submitted_at",)
        indexes = [models.Index(fields=("campaign", "target"), name="evaluation_ballot_aggregate")]

    def save(self, *args, **kwargs):
        if self.pk and type(self).objects.filter(pk=self.pk).exists():
            raise ValidationError("Las respuestas enviadas son inmutables.")
        if self.target_id and self.campaign_id and self.target.campaign_id != self.campaign_id:
            raise ValidationError("La respuesta y el objetivo deben pertenecer a la misma campaña.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Las respuestas enviadas no se pueden eliminar.")


class EvaluationAggregate(models.Model):
    class State(models.TextChoices):
        PUBLISHED = "published", "Publicable"
        SUPPRESSED = "suppressed", "Suprimido por mínimo de privacidad"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    campaign = models.ForeignKey(EvaluationCampaign, on_delete=models.PROTECT, related_name="aggregates")
    target = models.ForeignKey(EvaluationTarget, on_delete=models.PROTECT, related_name="aggregates")
    response_count = models.PositiveIntegerField()
    metrics = models.JSONField()
    state = models.CharField(max_length=12, choices=State.choices)
    published_at = models.DateTimeField()

    class Meta:
        constraints = [models.UniqueConstraint(fields=("campaign", "target"), name="uniq_evaluation_aggregate_target")]

    def save(self, *args, **kwargs):
        if self.pk and type(self).objects.filter(pk=self.pk).exists():
            raise ValidationError("Los agregados publicados son inmutables.")
        if self.target_id and self.campaign_id and self.target.campaign_id != self.campaign_id:
            raise ValidationError("El agregado y el objetivo deben pertenecer a la misma campaña.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Los agregados publicados no se pueden eliminar.")
