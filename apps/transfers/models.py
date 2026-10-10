import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from apps.academics.models import Enrollment
from apps.activities.models import Activity, PointsMovement


class TransferRequest(models.Model):
    class Status(models.TextChoices):
        IN_REVIEW = "in_review", "En revisión"
        FLAGGED = "flagged", "Revisión prioritaria"
        APPROVED = "approved", "Aprobada"
        REJECTED = "rejected", "Rechazada"
        CANCELLED = "cancelled", "Cancelada"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sender = models.ForeignKey(Enrollment, on_delete=models.PROTECT, related_name="transfer_requests_sent")
    recipient = models.ForeignKey(Enrollment, on_delete=models.PROTECT, related_name="transfer_requests_received")
    activity = models.ForeignKey(Activity, on_delete=models.PROTECT, related_name="transfer_requests")
    amount = models.PositiveSmallIntegerField()
    reason = models.CharField(max_length=500)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.IN_REVIEW)
    idempotency_key = models.CharField(max_length=64)
    risk_flags = models.JSONField(default=list, blank=True)
    submitted_at = models.DateTimeField(auto_now_add=True)
    resolved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="transfer_requests_resolved")
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-submitted_at",)
        constraints = [
            models.CheckConstraint(condition=Q(amount__gt=0), name="transfer_request_amount_positive"),
            models.CheckConstraint(condition=~Q(sender= models.F("recipient")), name="transfer_request_distinct_enrollments"),
            models.UniqueConstraint(fields=("sender", "idempotency_key"), name="uniq_transfer_sender_idempotency"),
            models.UniqueConstraint(fields=("sender", "recipient", "activity"), condition=~Q(status__in=("rejected", "cancelled")), name="uniq_active_transfer_recognition"),
        ]

    def clean(self):
        super().clean()
        if self.sender_id and self.recipient_id:
            if self.sender_id == self.recipient_id or self.sender.student_id == self.recipient.student_id:
                raise ValidationError("No puedes transferirte puntos a ti mismo.")
            if self.sender.career_id != self.recipient.career_id:
                raise ValidationError("La transferencia debe ser entre matrículas de la misma carrera.")
        if self.activity_id and self.sender_id:
            if self.activity.enrollment_id != self.sender_id:
                raise ValidationError("La actividad de colaboración debe pertenecer a tu matrícula.")
            if not self.activity.category.transferable:
                raise ValidationError("La categoría de esta actividad no permite transferencias.")
        if not self.reason.strip() or len(self.reason.strip()) < 10:
            raise ValidationError({"reason": "Explica la colaboración en al menos diez caracteres."})


class TransferAllocation(models.Model):
    """Reserve a portion of an immutable, transferable merit award."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    request = models.ForeignKey(TransferRequest, on_delete=models.PROTECT, related_name="allocations")
    source_movement = models.ForeignKey(PointsMovement, on_delete=models.PROTECT, related_name="transfer_allocations")
    amount = models.PositiveSmallIntegerField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("request", "source_movement"), name="uniq_transfer_source_per_request"),
            models.CheckConstraint(condition=Q(amount__gt=0), name="transfer_allocation_positive"),
        ]


class TransferMovement(models.Model):
    class Side(models.TextChoices):
        DEBIT = "debit", "Enviado"
        CREDIT = "credit", "Recibido"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    request = models.ForeignKey(TransferRequest, on_delete=models.PROTECT, related_name="movements")
    source_movement = models.ForeignKey(PointsMovement, on_delete=models.PROTECT, related_name="transferred_movements")
    enrollment = models.ForeignKey(Enrollment, on_delete=models.PROTECT, related_name="transfer_movements")
    side = models.CharField(max_length=8, choices=Side.choices)
    points = models.SmallIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(fields=("request", "source_movement", "side"), name="uniq_transfer_movement_pair"),
            models.CheckConstraint(condition=Q(points__lt=0) | Q(points__gt=0), name="transfer_movement_nonzero"),
            models.CheckConstraint(condition=~Q(side="debit") | Q(points__lt=0), name="transfer_debit_negative"),
            models.CheckConstraint(condition=~Q(side="credit") | Q(points__gt=0), name="transfer_credit_positive"),
        ]

    def save(self, *args, **kwargs):
        if self.pk and type(self).objects.filter(pk=self.pk).exists():
            raise ValidationError("Los movimientos de transferencia son inmutables.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Los movimientos de transferencia no se pueden eliminar.")


class TransferAdjustment(models.Model):
    """Append-only compensating line linked to an original transfer movement and risk review."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    alert = models.ForeignKey("TransferRiskAlert", on_delete=models.PROTECT, related_name="adjustments")
    original_movement = models.OneToOneField(TransferMovement, on_delete=models.PROTECT, related_name="adjustment")
    enrollment = models.ForeignKey(Enrollment, on_delete=models.PROTECT, related_name="transfer_adjustments")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="transfer_adjustments_created")
    points = models.SmallIntegerField()
    reason = models.CharField(max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("created_at",)
        constraints = [models.CheckConstraint(condition=~Q(points=0), name="transfer_adjustment_nonzero")]

    def save(self, *args, **kwargs):
        if self.pk and type(self).objects.filter(pk=self.pk).exists():
            raise ValidationError("Los ajustes de transferencia son inmutables.")
        if self.original_movement_id and self.points != -self.original_movement.points:
            raise ValidationError("El ajuste debe compensar exactamente el movimiento original.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Los ajustes de transferencia no se pueden eliminar.")


class TransferReview(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    request = models.ForeignKey(TransferRequest, on_delete=models.PROTECT, related_name="reviews")
    reviewer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="transfer_reviews")
    decision = models.CharField(max_length=8, choices=(("approve", "Aprobar"), ("reject", "Rechazar")))
    reason = models.CharField(max_length=500)
    decided_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("decided_at",)

    def save(self, *args, **kwargs):
        if self.pk and type(self).objects.filter(pk=self.pk).exists():
            raise ValidationError("Las revisiones de transferencia son inmutables.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Las revisiones de transferencia no se pueden eliminar.")


class TransferRiskAlert(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", "Pendiente"
        RESOLVED = "resolved", "Resuelta"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    request = models.ForeignKey(TransferRequest, on_delete=models.PROTECT, related_name="risk_alerts")
    code = models.CharField(max_length=48)
    description = models.CharField(max_length=300)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.OPEN)
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="transfer_risk_alerts_resolved")
    resolution_reason = models.CharField(max_length=500, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("request", "code"), name="uniq_transfer_risk_per_request")]
