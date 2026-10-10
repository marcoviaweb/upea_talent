from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import RoleAssignment
from apps.accounts.permissions import current_role_assignments, visible_course_enrollments
from apps.academics.models import CourseEnrollment, Enrollment, GradeRecord
from apps.audit.services import record_event

from .models import DevelopmentRecord, StudentProject, StudentSkill


def student_enrollments(user):
    if not getattr(user, "is_authenticated", False) or not user.is_active:
        return Enrollment.objects.none()
    career_ids = current_role_assignments(user).filter(
        role=RoleAssignment.Role.STUDENT, scope=RoleAssignment.Scope.CAREER
    ).values("career_id")
    return Enrollment.objects.filter(student__user=user, career_id__in=career_ids).select_related(
        "student__user", "career__institution", "period"
    )


def enrollment_for_actor(user, enrollment_id):
    own = student_enrollments(user).filter(pk=enrollment_id).first()
    if own:
        return own
    authorized_roster_row = visible_course_enrollments(user).filter(enrollment_id=enrollment_id).select_related(
        "enrollment__student__user", "enrollment__career", "enrollment__period", "enrollment__student__institution"
    ).first()
    if authorized_roster_row:
        return authorized_roster_row.enrollment
    raise Http404("Trayectoria no encontrada.")


def _is_enrollment_owner(user, enrollment):
    return enrollment.student.user_id == user.pk and student_enrollments(user).filter(pk=enrollment.pk).exists()


def save_development_record(*, actor, enrollment, record, submit=False):
    if not _is_enrollment_owner(actor, enrollment):
        raise PermissionDenied("Solo puedes declarar información en tu propia matrícula activa autorizada.")
    if enrollment.status != Enrollment.Status.ACTIVE:
        raise PermissionDenied("La matrícula está cerrada y solo permite consulta histórica.")
    with transaction.atomic():
        if not record._state.adding:
            existing = type(record).objects.select_for_update().get(pk=record.pk, enrollment=enrollment)
            if existing.status not in {DevelopmentRecord.Status.DECLARED, DevelopmentRecord.Status.NEEDS_CHANGES}:
                raise ValidationError("El registro ya está en revisión o validado y no se puede editar.")
            record.status = existing.status
            record.created_by = existing.created_by
            record.validated_by = None
            record.validated_at = None
            record.review_note = ""
        else:
            record.enrollment = enrollment
            record.created_by = actor
            record.status = DevelopmentRecord.Status.DECLARED
        if submit:
            record.status = DevelopmentRecord.Status.IN_REVIEW
        record.full_clean()
        record.save()
        record_event(
            actor=actor,
            action="trajectory.development_submitted" if submit else "trajectory.development_saved",
            obj=record,
            scope_type="career",
            scope_id=enrollment.career_id,
            reason="Declaración de trayectoria estudiantil",
            safe_metadata={"record_type": record._meta.model_name, "status": record.status},
        )
    return record


def review_development_record(*, actor, record, outcome, note=""):
    if outcome not in {"approve", "observe"}:
        raise ValidationError({"outcome": "Selecciona una decisión válida."})
    if actor.pk == record.created_by_id:
        raise PermissionDenied("No puedes validar tu propia declaración.")
    if record.status != DevelopmentRecord.Status.IN_REVIEW:
        raise ValidationError("Solo se pueden revisar declaraciones en revisión.")
    if outcome == "observe" and not note.strip():
        raise ValidationError({"note": "Explica qué información debe corregirse."})

    current_roles = current_role_assignments(actor).filter(
        scope=RoleAssignment.Scope.GROUP,
        role__in=(RoleAssignment.Role.TEACHER, RoleAssignment.Role.EVIDENCE_REVIEWER),
    )
    assigned_group_ids = current_roles.values("group_id")
    from django.db.models import Q
    roster = CourseEnrollment.objects.filter(
        enrollment=record.enrollment,
        active=True,
        offering_id__in=assigned_group_ids,
        offering__teaching_assignments__user=actor,
        offering__teaching_assignments__active=True,
        offering__teaching_assignments__starts_on__lte=timezone.localdate(),
    ).filter(
        models_q_assignment_end()
    ).filter(
        Q(offering__teaching_assignments__role="teacher", offering__role_assignments__role=RoleAssignment.Role.TEACHER)
        | Q(offering__teaching_assignments__role="auxiliary", offering__role_assignments__role=RoleAssignment.Role.EVIDENCE_REVIEWER)
    ).filter(offering__role_assignments__user=actor, offering__role_assignments__active=True)
    if not roster.exists():
        raise PermissionDenied("La revisión requiere una asignación vigente al grupo de esta matrícula.")

    with transaction.atomic():
        record = type(record).objects.select_for_update().get(pk=record.pk)
        if record.status != DevelopmentRecord.Status.IN_REVIEW:
            raise ValidationError("Otro usuario ya resolvió esta declaración.")
        if outcome == "approve":
            record.status = DevelopmentRecord.Status.VALIDATED
            record.validated_by = actor
            record.validated_at = timezone.now()
            record.review_note = note.strip()
        else:
            record.status = DevelopmentRecord.Status.NEEDS_CHANGES
            record.validated_by = None
            record.validated_at = None
            record.review_note = note.strip()
        record.full_clean()
        record.save(update_fields=("status", "validated_by", "validated_at", "review_note", "updated_at"))
        record_event(
            actor=actor,
            action="trajectory.development_validated" if outcome == "approve" else "trajectory.development_observed",
            obj=record,
            scope_type="career",
            scope_id=record.enrollment.career_id,
            reason="Revisión de declaración de trayectoria",
            safe_metadata={"record_type": record._meta.model_name, "status": record.status},
        )
    return record


def models_q_assignment_end():
    from django.db.models import Q
    return Q(offering__teaching_assignments__ends_on__isnull=True) | Q(offering__teaching_assignments__ends_on__gte=timezone.localdate())


def create_grade_record(*, actor, enrollment, offering, grade_value, source, source_reference="", reason=""):
    if enrollment.career_id != offering.course.career_id or enrollment.period_id != offering.period_id:
        raise ValidationError("La asignatura no corresponde a la carrera y periodo de la matrícula.")
    can_administer = current_role_assignments(actor).filter(
        role=RoleAssignment.Role.CAREER_ADMIN,
        scope=RoleAssignment.Scope.CAREER,
        career_id=enrollment.career_id,
    ).exists()
    can_teach = visible_course_enrollments(actor).filter(enrollment=enrollment, offering=offering).exists() and current_role_assignments(actor).filter(
        role=RoleAssignment.Role.TEACHER, scope=RoleAssignment.Scope.GROUP, group=offering,
    ).exists()
    if not (can_administer or can_teach):
        raise PermissionDenied("Solo administración de carrera o docente asignado puede registrar notas.")
    if not source.strip():
        raise ValidationError({"source": "Indica el origen verificable de la nota."})
    grade = GradeRecord(
        enrollment=enrollment,
        offering=offering,
        grade_value=grade_value,
        scale_snapshot=enrollment.period.grade_scale,
        pass_threshold_snapshot=enrollment.period.pass_threshold,
        status=GradeRecord.Status.VERIFIED,
        source=source.strip(),
        source_reference=source_reference.strip(),
        recorded_by=actor,
        verified_by=actor,
        verified_at=timezone.now(),
    )
    with transaction.atomic():
        locked_enrollment = Enrollment.objects.select_for_update().get(pk=enrollment.pk)
        previous = GradeRecord.objects.filter(enrollment=locked_enrollment, offering=offering, revisions__isnull=True).order_by("-created_at").first()
        if previous:
            grade.supersedes = previous
            grade.full_clean()
            previous.status = GradeRecord.Status.SUPERSEDED
            previous.save(update_fields=("status", "updated_at"))
        else:
            grade.full_clean()
        grade.save()
        record_event(
            actor=actor,
            action="academics.grade_recorded" if not previous else "academics.grade_corrected",
            obj=grade,
            scope_type="career",
            scope_id=enrollment.career_id,
            reason=reason.strip() or "Registro académico verificado",
            safe_metadata={"offering_id": str(offering.pk), "grade_status": grade.status},
        )
    return grade


def validated_development_counts(enrollment):
    return {
        "projects": StudentProject.objects.filter(enrollment=enrollment, status=DevelopmentRecord.Status.VALIDATED).count(),
        "skills": StudentSkill.objects.filter(enrollment=enrollment, status=DevelopmentRecord.Status.VALIDATED).count(),
    }
