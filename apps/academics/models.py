import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class UUIDModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Institution(UUIDModel):
    name = models.CharField(max_length=180)
    short_name = models.CharField(max_length=40, unique=True)
    timezone = models.CharField(max_length=64, default="America/La_Paz")
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ("name",)
        verbose_name = "institución"
        verbose_name_plural = "instituciones"

    def __str__(self):
        return self.short_name


class Career(UUIDModel):
    institution = models.ForeignKey(Institution, on_delete=models.PROTECT, related_name="careers")
    code = models.CharField(max_length=24)
    name = models.CharField(max_length=180)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ("name",)
        constraints = [models.UniqueConstraint(fields=("institution", "code"), name="uniq_career_code_per_institution")]

    def __str__(self):
        return self.name


class AcademicPeriod(UUIDModel):
    class Status(models.TextChoices):
        PLANNED = "planned", "Planificado"
        OPEN = "open", "Abierto"
        CLOSED = "closed", "Cerrado"

    career = models.ForeignKey(Career, on_delete=models.PROTECT, related_name="periods")
    code = models.CharField(max_length=32)
    name = models.CharField(max_length=120)
    starts_on = models.DateField()
    ends_on = models.DateField()
    grade_scale = models.DecimalField(max_digits=5, decimal_places=2, default=100)
    pass_threshold = models.DecimalField(max_digits=5, decimal_places=2, default=51)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PLANNED)

    class Meta:
        ordering = ("-starts_on",)
        constraints = [
            models.UniqueConstraint(fields=("career", "code"), name="uniq_period_code_per_career"),
            models.CheckConstraint(condition=models.Q(ends_on__gte=models.F("starts_on")), name="academic_period_dates_ordered"),
            models.CheckConstraint(condition=models.Q(grade_scale__gt=0), name="academic_period_scale_positive"),
            models.CheckConstraint(condition=models.Q(pass_threshold__gte=0) & models.Q(pass_threshold__lte=models.F("grade_scale")), name="academic_period_pass_within_scale"),
        ]

    def __str__(self):
        return f"{self.career.code} · {self.name}"


class Course(UUIDModel):
    career = models.ForeignKey(Career, on_delete=models.PROTECT, related_name="courses")
    code = models.CharField(max_length=24)
    name = models.CharField(max_length=180)
    credits = models.PositiveSmallIntegerField(default=0)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ("code",)
        constraints = [models.UniqueConstraint(fields=("career", "code"), name="uniq_course_code_per_career")]

    def __str__(self):
        return f"{self.code} · {self.name}"


class CourseOffering(UUIDModel):
    class Status(models.TextChoices):
        PLANNED = "planned", "Planificado"
        OPEN = "open", "Abierto"
        CLOSED = "closed", "Cerrado"

    course = models.ForeignKey(Course, on_delete=models.PROTECT, related_name="offerings")
    period = models.ForeignKey(AcademicPeriod, on_delete=models.PROTECT, related_name="offerings")
    group_code = models.CharField(max_length=24)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PLANNED)

    class Meta:
        ordering = ("period__starts_on", "course__code", "group_code")
        constraints = [models.UniqueConstraint(fields=("course", "period", "group_code"), name="uniq_course_offering_group")]

    def clean(self):
        super().clean()
        if self.course_id and self.period_id and self.course.career_id != self.period.career_id:
            raise ValidationError("La asignatura y el periodo deben pertenecer a la misma carrera.")

    def __str__(self):
        return f"{self.course.code} · {self.group_code} · {self.period.code}"


class StudentProfile(UUIDModel):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="student_profile")
    institution = models.ForeignKey(Institution, on_delete=models.PROTECT, related_name="students")
    student_number = models.CharField(max_length=32)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("institution", "student_number"), name="uniq_student_number_per_institution")]

    def __str__(self):
        return f"{self.student_number} · {self.user.get_full_name()}"


class Enrollment(UUIDModel):
    class Status(models.TextChoices):
        ACTIVE = "active", "Activa"
        COMPLETED = "completed", "Concluida"
        WITHDRAWN = "withdrawn", "Retirada"
        CANCELLED = "cancelled", "Cancelada"

    student = models.ForeignKey(StudentProfile, on_delete=models.PROTECT, related_name="enrollments")
    career = models.ForeignKey(Career, on_delete=models.PROTECT, related_name="enrollments")
    period = models.ForeignKey(AcademicPeriod, on_delete=models.PROTECT, related_name="enrollments")
    semester_number = models.PositiveSmallIntegerField(default=1)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.ACTIVE)
    valid_from = models.DateField()
    valid_to = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ("-period__starts_on", "student__student_number")
        constraints = [
            models.UniqueConstraint(fields=("student", "career", "period"), name="uniq_student_enrollment_per_period"),
            models.CheckConstraint(condition=models.Q(valid_to__isnull=True) | models.Q(valid_to__gte=models.F("valid_from")), name="enrollment_valid_dates"),
        ]

    def clean(self):
        super().clean()
        if self.career_id and self.period_id and self.career_id != self.period.career_id:
            raise ValidationError({"period": "El periodo debe pertenecer a la carrera de la matrícula."})
        if self.student_id and self.career_id and self.student.institution_id != self.career.institution_id:
            raise ValidationError({"career": "La carrera debe pertenecer a la institución del estudiante."})

    def __str__(self):
        return f"{self.student.student_number} · {self.career.code} · {self.period.code}"


class CourseEnrollment(UUIDModel):
    """Enrollment in a course group, providing a concrete roster boundary."""
    enrollment = models.ForeignKey(Enrollment, on_delete=models.PROTECT, related_name="course_enrollments")
    offering = models.ForeignKey(CourseOffering, on_delete=models.PROTECT, related_name="roster")
    active = models.BooleanField(default=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("enrollment", "offering"), name="uniq_enrollment_per_offering")]

    def clean(self):
        super().clean()
        if self.enrollment_id and self.offering_id:
            if self.enrollment.career_id != self.offering.course.career_id or self.enrollment.period_id != self.offering.period_id:
                raise ValidationError("La matrícula y el grupo deben coincidir en carrera y periodo.")


class TeachingAssignment(UUIDModel):
    class AssignmentRole(models.TextChoices):
        TEACHER = "teacher", "Docente"
        AUXILIARY = "auxiliary", "Auxiliar"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="teaching_assignments")
    offering = models.ForeignKey(CourseOffering, on_delete=models.PROTECT, related_name="teaching_assignments")
    role = models.CharField(max_length=12, choices=AssignmentRole.choices)
    starts_on = models.DateField()
    ends_on = models.DateField(null=True, blank=True)
    active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("user", "offering", "role"), condition=models.Q(active=True), name="uniq_active_teaching_assignment"),
            models.CheckConstraint(condition=models.Q(ends_on__isnull=True) | models.Q(ends_on__gte=models.F("starts_on")), name="teaching_assignment_valid_dates"),
        ]

    def clean(self):
        super().clean()
        expected_role = {self.AssignmentRole.TEACHER: "teacher", self.AssignmentRole.AUXILIARY: "auxiliary"}.get(self.role)
        if expected_role and self.user_id and not self.user.role_assignments.filter(role=expected_role, scope="group", group_id=self.offering_id, active=True).exists():
            raise ValidationError({"user": "El usuario requiere un rol vigente asignado a este grupo."})


class GradeRecord(UUIDModel):
    class Status(models.TextChoices):
        UNVERIFIED = "unverified", "Sin verificar"
        VERIFIED = "verified", "Verificada"
        SUPERSEDED = "superseded", "Reemplazada"

    enrollment = models.ForeignKey(Enrollment, on_delete=models.PROTECT, related_name="grade_records")
    offering = models.ForeignKey(CourseOffering, on_delete=models.PROTECT, related_name="grade_records")
    grade_value = models.DecimalField(max_digits=5, decimal_places=2)
    scale_snapshot = models.DecimalField(max_digits=5, decimal_places=2)
    pass_threshold_snapshot = models.DecimalField(max_digits=5, decimal_places=2, default=51)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.UNVERIFIED)
    source = models.CharField(max_length=120, blank=True)
    source_reference = models.CharField(max_length=160, blank=True)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="grade_records_created")
    verified_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="grade_records_verified")
    verified_at = models.DateTimeField(null=True, blank=True)
    supersedes = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT, related_name="revisions")

    class Meta:
        ordering = ("offering__period__starts_on", "offering__course__code")
        constraints = [
            models.CheckConstraint(condition=models.Q(scale_snapshot__gt=0), name="grade_scale_positive"),
            models.UniqueConstraint(fields=("enrollment", "offering"), condition=models.Q(supersedes__isnull=True), name="uniq_original_grade_per_course_enrollment"),
            models.UniqueConstraint(fields=("supersedes",), condition=models.Q(supersedes__isnull=False), name="uniq_direct_grade_revision"),
            models.CheckConstraint(condition=models.Q(grade_value__gte=0) & models.Q(grade_value__lte=models.F("scale_snapshot")), name="grade_within_scale"),
            models.CheckConstraint(condition=models.Q(pass_threshold_snapshot__gte=0) & models.Q(pass_threshold_snapshot__lte=models.F("scale_snapshot")), name="grade_pass_threshold_within_scale"),
        ]

    def clean(self):
        super().clean()
        if self.enrollment_id and self.offering_id:
            if self.enrollment.career_id != self.offering.course.career_id or self.enrollment.period_id != self.offering.period_id:
                raise ValidationError("La nota y la matrícula deben pertenecer a la misma carrera y periodo.")
            if self.scale_snapshot > 0 and self.grade_value > self.scale_snapshot:
                raise ValidationError({"grade_value": "La nota supera la escala registrada."})
            if self.pass_threshold_snapshot > self.scale_snapshot:
                raise ValidationError({"pass_threshold_snapshot": "El criterio de aprobación supera la escala registrada."})
        if self.status == self.Status.VERIFIED and (not self.verified_by_id or not self.verified_at):
            raise ValidationError("Una nota verificada debe indicar responsable y fecha de verificación.")
        if self.status == self.Status.UNVERIFIED and (self.verified_by_id or self.verified_at):
            raise ValidationError("Una nota sin verificar no puede guardar responsable o fecha de verificación.")
        if self.supersedes_id and (
            self.supersedes.enrollment_id != self.enrollment_id
            or self.supersedes.offering_id != self.offering_id
        ):
            raise ValidationError({"supersedes": "La revisión debe conservar la matrícula y asignatura originales."})
