import uuid
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.storage import FileSystemStorage
from django.db import models

from apps.academics.models import Career, Enrollment


private_evidence_storage = FileSystemStorage(location=Path(settings.BASE_DIR) / "private_uploads" / "evidence")


class Regulation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    career = models.ForeignKey(Career, on_delete=models.PROTECT, related_name="spd_regulations")
    version = models.PositiveSmallIntegerField()
    title = models.CharField(max_length=160)
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)
    published = models.BooleanField(default=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="spd_regulations_created")
    published_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="spd_regulations_published")
    published_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("career__code", "-version")
        constraints = [models.UniqueConstraint(fields=("career", "version"), name="uniq_spd_regulation_version")]

    def clean(self):
        if self.effective_to and self.effective_to < self.effective_from:
            raise ValidationError({"effective_to": "La vigencia final no puede preceder a la inicial."})
        if self.published and self.pk and type(self).objects.filter(pk=self.pk, published=True).exists():
            original = type(self).objects.get(pk=self.pk)
            protected = ("career_id", "version", "title", "effective_from", "effective_to", "published")
            if any(getattr(original, field) != getattr(self, field) for field in protected):
                raise ValidationError("Una versión publicada es inmutable; crea una nueva versión.")

    def save(self, *args, **kwargs):
        if self.pk:
            original = type(self).objects.filter(pk=self.pk, published=True).first()
            if original:
                protected = ("career_id", "version", "title", "effective_from", "effective_to", "published")
                if any(getattr(original, field) != getattr(self, field) for field in protected):
                    raise ValidationError("Una versión publicada es inmutable; crea una nueva versión.")
        return super().save(*args, **kwargs)


class ActivityCategory(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    regulation = models.ForeignKey(Regulation, on_delete=models.PROTECT, related_name="categories")
    code = models.SlugField(max_length=48)
    name = models.CharField(max_length=120)
    criterion = models.CharField(max_length=500)
    points = models.PositiveSmallIntegerField()
    transferable = models.BooleanField(default=False)
    active = models.BooleanField(default=True)
    reviewer_roles = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ("name",)
        constraints = [models.UniqueConstraint(fields=("regulation", "code"), name="uniq_category_code_per_regulation")]

    def save(self, *args, **kwargs):
        previous = type(self).objects.filter(pk=self.pk).first() if self.pk else None
        if self.regulation_id and self.regulation.published and previous:
            if previous and any(getattr(previous, field) != getattr(self, field) for field in ("code", "name", "criterion", "points", "transferable", "active", "reviewer_roles")):
                raise ValidationError("Las categorías publicadas son inmutables; crea una nueva versión del reglamento.")
        if self.regulation_id and self.regulation.published and not previous:
            raise ValidationError("No se pueden agregar categorías a un reglamento publicado.")
        return super().save(*args, **kwargs)


class Activity(models.Model):
    class Status(models.TextChoices):
        IN_REVIEW = "in_review", "En revisión"
        OBSERVED = "observed", "Observada"
        APPROVED = "approved", "Aprobada"
        REJECTED = "rejected", "Rechazada"
        REVOKED = "revoked", "Revocada"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    enrollment = models.ForeignKey(Enrollment, on_delete=models.PROTECT, related_name="activities")
    category = models.ForeignKey(ActivityCategory, on_delete=models.PROTECT, related_name="activities")
    title = models.CharField(max_length=160)
    description = models.TextField(max_length=3000)
    occurred_on = models.DateField()
    source = models.CharField(max_length=200, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="activities_created")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.IN_REVIEW)
    assigned_group = models.ForeignKey("academics.CourseOffering", null=True, blank=True, on_delete=models.PROTECT, related_name="evidence_activities")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="activities_reviewed")
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [models.UniqueConstraint(fields=("enrollment", "occurred_on", "title"), condition=~models.Q(status="rejected"), name="uniq_active_activity_fact")]

    def clean(self):
        if self.enrollment_id and self.category_id and self.enrollment.career_id != self.category.regulation.career_id:
            raise ValidationError({"category": "La categoría no pertenece a la carrera de la matrícula."})
        if self.assigned_group_id and self.enrollment_id:
            if not self.enrollment.course_enrollments.filter(offering_id=self.assigned_group_id, active=True).exists():
                raise ValidationError({"assigned_group": "El grupo no pertenece a la matrícula."})


class EvidenceFile(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    activity = models.ForeignKey(Activity, on_delete=models.PROTECT, related_name="files")
    file = models.FileField(storage=private_evidence_storage, upload_to="")
    original_name = models.CharField(max_length=255)
    content_type = models.CharField(max_length=80)
    size = models.PositiveIntegerField()
    version = models.PositiveSmallIntegerField(default=1)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="evidence_files_uploaded")
    uploaded_at = models.DateTimeField(auto_now_add=True)


class ReviewDecision(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    activity = models.ForeignKey(Activity, on_delete=models.PROTECT, related_name="reviews")
    reviewer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="evidence_decisions")
    outcome = models.CharField(max_length=16, choices=(("approve", "Aprobar"), ("observe", "Observar"), ("reject", "Rechazar"), ("revoke", "Revocar")))
    note = models.CharField(max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("created_at",)


class PointsMovement(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    enrollment = models.ForeignKey(Enrollment, on_delete=models.PROTECT, related_name="spd_movements")
    activity = models.ForeignKey(Activity, null=True, blank=True, on_delete=models.PROTECT, related_name="point_movements")
    regulation = models.ForeignKey(Regulation, on_delete=models.PROTECT, related_name="movements")
    category = models.ForeignKey(ActivityCategory, on_delete=models.PROTECT, related_name="movements")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="spd_movements_created")
    points = models.SmallIntegerField()
    reason = models.CharField(max_length=300)
    reversal_of = models.OneToOneField("self", null=True, blank=True, on_delete=models.PROTECT, related_name="reversal")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [models.UniqueConstraint(fields=("activity",), condition=models.Q(activity__isnull=False, reversal_of__isnull=True), name="uniq_spd_award_per_activity")]

    def save(self, *args, **kwargs):
        if self.pk and type(self).objects.filter(pk=self.pk).exists():
            raise ValidationError("Los movimientos SPD son inmutables; registra un ajuste compensatorio.")
        if self.reversal_of_id and self.points != -self.reversal_of.points:
            raise ValidationError("La reversión debe compensar exactamente el movimiento original.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Los movimientos SPD no se pueden eliminar.")
