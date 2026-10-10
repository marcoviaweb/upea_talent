import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q


class Opportunity(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Borrador"
        PUBLISHED = "published", "Publicada"
        CLOSED = "closed", "Cerrada"
        RESOLVED = "resolved", "Resuelta"
        CANCELLED = "cancelled", "Cancelada"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="owned_opportunities")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="opportunities_created")
    active_version = models.ForeignKey("OpportunityVersion", null=True, blank=True, on_delete=models.PROTECT, related_name="active_for_opportunities")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)


class OpportunityVersion(models.Model):
    class Kind(models.TextChoices):
        SCHOLARSHIP = "scholarship", "Beca"
        INTERNSHIP = "internship", "Pasantía"
        COURSE = "course", "Curso"
        CONTEST = "contest", "Concurso"
        PROJECT = "project", "Proyecto"
        EXCHANGE = "exchange", "Intercambio"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    opportunity = models.ForeignKey(Opportunity, on_delete=models.PROTECT, related_name="versions")
    version_number = models.PositiveSmallIntegerField()
    title = models.CharField(max_length=160)
    kind = models.CharField(max_length=16, choices=Kind.choices)
    description = models.TextField(max_length=4000)
    benefits = models.TextField(max_length=2000, blank=True)
    application_instructions = models.TextField(max_length=2000, blank=True)
    opens_at = models.DateTimeField()
    closes_at = models.DateTimeField()
    capacity = models.PositiveSmallIntegerField()
    careers = models.ManyToManyField("academics.Career", related_name="opportunity_versions")
    published_at = models.DateTimeField(null=True, blank=True)
    published_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="opportunity_versions_published")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-version_number",)
        constraints = [
            models.UniqueConstraint(fields=("opportunity", "version_number"), name="uniq_opportunity_version_number"),
            models.CheckConstraint(condition=Q(capacity__gt=0), name="opportunity_capacity_positive"),
            models.CheckConstraint(condition=Q(closes_at__gt=models.F("opens_at")), name="opportunity_dates_ordered"),
        ]

    def save(self, *args, **kwargs):
        if self.pk and type(self).objects.filter(pk=self.pk, published_at__isnull=False).exists():
            raise ValidationError("Una versión publicada es inmutable; crea una versión nueva.")
        return super().save(*args, **kwargs)


class OpportunityRequirement(models.Model):
    class Field(models.TextChoices):
        AVERAGE = "average", "Promedio simple verificado"
        OWN_POINTS = "own_points", "Puntos SPD propios"
        SEMESTER = "semester", "Semestre mínimo"
        PERIOD = "period", "Periodo académico"
        VALIDATED_PROJECT = "validated_project", "Proyecto validado"
        VALIDATED_ACTIVITY = "validated_activity", "Actividad verificada"
        APPROVED_COURSE = "approved_course", "Curso aprobado"
        VALIDATED_SKILL = "validated_skill", "Habilidad validada"

    class Operator(models.TextChoices):
        GTE = "gte", "Al menos"
        EXACT = "exact", "Igual a"
        EXISTS = "exists", "Debe existir"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    version = models.ForeignKey(OpportunityVersion, on_delete=models.PROTECT, related_name="requirements")
    field_code = models.CharField(max_length=24, choices=Field.choices)
    operator = models.CharField(max_length=8, choices=Operator.choices)
    target_number = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    course_code = models.CharField(max_length=24, blank=True)
    academic_period_code = models.CharField(max_length=32, blank=True)
    display_label = models.CharField(max_length=180)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ("sort_order", "id")
        constraints = [models.UniqueConstraint(fields=("version", "field_code", "course_code"), name="uniq_requirement_per_version_field_course")]

    def clean(self):
        super().clean()
        numeric_fields = {self.Field.AVERAGE, self.Field.OWN_POINTS, self.Field.SEMESTER}
        if self.field_code in numeric_fields:
            if self.operator != self.Operator.GTE or self.target_number is None:
                raise ValidationError("Este criterio requiere un umbral numérico.")
            if self.target_number < 0 or (self.field_code == self.Field.AVERAGE and self.target_number > 100) or (self.field_code == self.Field.SEMESTER and self.target_number < 1):
                raise ValidationError("El umbral debe estar en el rango válido para el criterio.")
            if self.field_code in {self.Field.OWN_POINTS, self.Field.SEMESTER} and self.target_number != self.target_number.to_integral_value():
                raise ValidationError("Los umbrales SPD y semestre deben ser números enteros.")
        elif self.field_code == self.Field.PERIOD:
            if self.operator != self.Operator.EXACT or not self.academic_period_code.strip():
                raise ValidationError("El periodo requiere un código y una comparación exacta.")
        elif self.operator != self.Operator.EXISTS:
            raise ValidationError("Este requisito solo admite comprobar existencia.")
        if (self.field_code == self.Field.APPROVED_COURSE) != bool(self.course_code):
            raise ValidationError({"course_code": "Solo el requisito de curso necesita un código de asignatura."})
        if (self.field_code == self.Field.PERIOD) != bool(self.academic_period_code):
            raise ValidationError({"academic_period_code": "Solo el requisito de periodo necesita un código académico."})

    def save(self, *args, **kwargs):
        if self.version_id and self.version.published_at:
            raise ValidationError("Los requisitos publicados son inmutables; crea una versión nueva.")
        self.full_clean()
        return super().save(*args, **kwargs)


class EligibilitySnapshot(models.Model):
    class Overall(models.TextChoices):
        ELIGIBLE = "eligible", "Cumple los requisitos"
        INELIGIBLE = "ineligible", "No cumple todos los requisitos"
        INSUFFICIENT = "insufficient", "Faltan datos verificados"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    version = models.ForeignKey(OpportunityVersion, on_delete=models.PROTECT, related_name="eligibility_snapshots")
    enrollment = models.ForeignKey("academics.Enrollment", on_delete=models.PROTECT, related_name="eligibility_snapshots")
    computed_at = models.DateTimeField(auto_now_add=True)
    overall_status = models.CharField(max_length=12, choices=Overall.choices)
    results = models.JSONField(default=list)
    input_fingerprint = models.CharField(max_length=64)


class Application(models.Model):
    class Status(models.TextChoices):
        SUBMITTED = "submitted", "Enviada"
        IN_REVIEW = "in_review", "En revisión"
        SELECTED = "selected", "Seleccionada"
        NOT_SELECTED = "not_selected", "No seleccionada"
        WITHDRAWN = "withdrawn", "Retirada"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    version = models.ForeignKey(OpportunityVersion, on_delete=models.PROTECT, related_name="applications")
    enrollment = models.ForeignKey("academics.Enrollment", on_delete=models.PROTECT, related_name="opportunity_applications")
    eligibility = models.ForeignKey(EligibilitySnapshot, on_delete=models.PROTECT, related_name="applications")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.SUBMITTED)
    submitted_at = models.DateTimeField(auto_now_add=True)
    withdrawn_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("submitted_at",)
        constraints = [models.UniqueConstraint(fields=("version", "enrollment"), condition=~Q(status="withdrawn"), name="uniq_active_opportunity_application")]


class ApplicationDecision(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    application = models.ForeignKey(Application, on_delete=models.PROTECT, related_name="decisions")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="application_decisions")
    previous_status = models.CharField(max_length=16, choices=Application.Status.choices)
    decision = models.CharField(max_length=16, choices=(("selected", "Seleccionar"), ("not_selected", "No seleccionar"), ("in_review", "En revisión")))
    reason = models.CharField(max_length=1000)
    resolution_eligibility = models.ForeignKey(EligibilitySnapshot, null=True, blank=True, on_delete=models.PROTECT, related_name="resolution_decisions")
    decided_at = models.DateTimeField(auto_now_add=True)
