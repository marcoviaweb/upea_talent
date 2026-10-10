import uuid

from django.contrib.auth.models import AbstractUser
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone


class User(AbstractUser):
    """Account identity; academic authority is granted separately by scope."""

    email = models.EmailField("correo electrónico", unique=True)


class RoleAssignment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    class Role(models.TextChoices):
        STUDENT = "student", "Estudiante"
        TEACHER = "teacher", "Docente"
        AUXILIARY = "auxiliary", "Auxiliar"
        COORDINATOR = "coordinator", "Coordinación"
        CAREER_ADMIN = "career_admin", "Administración de carrera"
        INSTITUTION_ADMIN = "institution_admin", "Administración institucional"
        EVIDENCE_REVIEWER = "evidence_reviewer", "Revisor de evidencia"
        OPPORTUNITY_OWNER = "opportunity_owner", "Responsable de oportunidad"

    class Scope(models.TextChoices):
        INSTITUTION = "institution", "Institución"
        CAREER = "career", "Carrera"
        GROUP = "group", "Grupo"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="role_assignments")
    role = models.CharField(max_length=32, choices=Role.choices)
    scope = models.CharField(max_length=16, choices=Scope.choices)
    institution = models.ForeignKey("academics.Institution", null=True, blank=True, on_delete=models.PROTECT, related_name="role_assignments")
    career = models.ForeignKey("academics.Career", null=True, blank=True, on_delete=models.PROTECT, related_name="role_assignments")
    group = models.ForeignKey("academics.CourseOffering", null=True, blank=True, on_delete=models.PROTECT, related_name="role_assignments")
    starts_at = models.DateField(default=timezone.localdate)
    ends_at = models.DateField(null=True, blank=True)
    active = models.BooleanField(default=True)
    granted_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="granted_role_assignments")
    reason = models.CharField(max_length=300)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("user_id", "role", "scope")
        constraints = [
            models.CheckConstraint(
                condition=(Q(scope="institution", institution__isnull=False, career__isnull=True, group__isnull=True)
                           | Q(scope="career", institution__isnull=True, career__isnull=False, group__isnull=True)
                           | Q(scope="group", institution__isnull=True, career__isnull=True, group__isnull=False)),
                name="role_assignment_one_scope_target",
            ),
            models.CheckConstraint(condition=Q(ends_at__isnull=True) | Q(ends_at__gte=models.F("starts_at")), name="role_assignment_valid_dates"),
            models.UniqueConstraint(fields=("user", "role", "institution"), condition=Q(active=True, scope="institution"), name="uniq_active_institution_role"),
            models.UniqueConstraint(fields=("user", "role", "career"), condition=Q(active=True, scope="career"), name="uniq_active_career_role"),
            models.UniqueConstraint(fields=("user", "role", "group"), condition=Q(active=True, scope="group"), name="uniq_active_group_role"),
        ]

    def clean(self):
        super().clean()
        expected = {"institution": self.institution_id, "career": self.career_id, "group": self.group_id}
        if self.scope and not expected.get(self.scope):
            raise ValidationError({self.scope: "El ámbito requiere una entidad asociada."})
        if self.scope == self.Scope.INSTITUTION and self.role != self.Role.INSTITUTION_ADMIN:
            raise ValidationError({"role": "El ámbito institucional se reserva para administración institucional."})
        if self.scope == self.Scope.CAREER and self.role not in {self.Role.STUDENT, self.Role.COORDINATOR, self.Role.CAREER_ADMIN}:
            raise ValidationError({"role": "Este rol requiere ámbito de grupo o institucional."})
        if self.scope == self.Scope.GROUP and self.group_id and self.role not in {self.Role.TEACHER, self.Role.AUXILIARY, self.Role.EVIDENCE_REVIEWER, self.Role.OPPORTUNITY_OWNER}:
            raise ValidationError({"role": "Este rol requiere ámbito de institución o carrera."})
        if self.scope == self.Scope.CAREER and self.career_id and self.institution_id:
            raise ValidationError({"institution": "La asignación de carrera solo registra la carrera."})

    def is_current(self, on_date=None):
        on_date = on_date or timezone.localdate()
        return self.active and self.starts_at <= on_date and (self.ends_at is None or self.ends_at >= on_date) and self.user.is_active
