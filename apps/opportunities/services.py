import hashlib
import json
from decimal import Decimal
from types import SimpleNamespace

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.accounts.models import RoleAssignment
from apps.accounts.permissions import current_role_assignments
from apps.academics.models import GradeRecord
from apps.activities.models import Activity, PointsMovement
from apps.audit.services import record_event
from apps.profiles.models import StudentProject, StudentSkill
from .models import (
    Application, ApplicationDecision, EligibilitySnapshot, Opportunity,
    OpportunityRequirement, OpportunityVersion,
)


def has_career_role(user, career, roles=None):
    assignments = current_role_assignments(user)
    if user.is_superuser or assignments.filter(
        active=True, scope=RoleAssignment.Scope.INSTITUTION,
        role=RoleAssignment.Role.INSTITUTION_ADMIN, institution=career.institution,
    ).exists():
        return True
    assignments = assignments.filter(
        active=True, scope=RoleAssignment.Scope.CAREER, career=career,
    ).exclude(role=RoleAssignment.Role.STUDENT)
    return assignments.exists() if roles is None else assignments.filter(role__in=roles).exists()


def can_manage_version(user, version):
    return version.opportunity.owner_id == user.pk or any(
        has_career_role(user, career, {RoleAssignment.Role.COORDINATOR, RoleAssignment.Role.CAREER_ADMIN})
        for career in version.careers.all()
    ) or user.is_superuser


def evaluate_eligibility(version, enrollment, *, persist=True):
    if not version.careers.filter(pk=enrollment.career_id).exists():
        raise PermissionDenied("La convocatoria no corresponde a la carrera de esta matrícula.")
    grades = list(GradeRecord.objects.filter(
        enrollment=enrollment, status=GradeRecord.Status.VERIFIED,
    ).select_related("offering__course").order_by("offering__course__code"))
    projects = StudentProject.objects.filter(enrollment=enrollment, status=StudentProject.Status.VALIDATED)
    skills = StudentSkill.objects.filter(enrollment=enrollment, status=StudentSkill.Status.VALIDATED)
    points = PointsMovement.objects.filter(enrollment=enrollment, activity__isnull=False).aggregate(total=Sum("points"))["total"] or 0
    results = []
    for requirement in version.requirements.all():
        current = None
        source = ""
        state = "insufficient"
        if requirement.field_code == OpportunityRequirement.Field.AVERAGE:
            if grades:
                normalized = [g.grade_value / g.scale_snapshot * Decimal("100") for g in grades]
                current = str((sum(normalized, Decimal(0)) / len(normalized)).quantize(Decimal("0.01")))
                source = f"Promedio simple no ponderado de {len(grades)} notas verificadas de {enrollment.period.code}, normalizadas a escala 100."
                state = "meets" if Decimal(current) >= requirement.target_number else "does_not_meet"
            else:
                source = f"No hay notas verificadas en {enrollment.period.code}."
        elif requirement.field_code == OpportunityRequirement.Field.OWN_POINTS:
            current = str(points)
            source = "Libro SPD de esta matrícula; solo movimientos propios, sin transferencias."
            state = "meets" if Decimal(current) >= requirement.target_number else "does_not_meet"
        elif requirement.field_code == OpportunityRequirement.Field.SEMESTER:
            current = enrollment.semester_number
            source = f"Matrícula activa de {enrollment.career.code}, periodo {enrollment.period.code}."
            state = "meets" if Decimal(current) >= requirement.target_number else "does_not_meet"
        elif requirement.field_code == OpportunityRequirement.Field.PERIOD:
            current = enrollment.period.code
            source = f"Periodo académico vigente de la matrícula en {enrollment.career.code}."
            state = "meets" if current == requirement.academic_period_code else "does_not_meet"
        elif requirement.field_code == OpportunityRequirement.Field.VALIDATED_PROJECT:
            item = projects.first()
            current = projects.count()
            source = f"{item.title} · validado el {item.validated_at.date().isoformat()}." if item else "Registro de proyectos validados de la matrícula."
            state = "meets" if current else "does_not_meet"
        elif requirement.field_code == OpportunityRequirement.Field.VALIDATED_ACTIVITY:
            item = Activity.objects.filter(enrollment=enrollment, status=Activity.Status.APPROVED).select_related("category").order_by("occurred_on").first()
            current = Activity.objects.filter(enrollment=enrollment, status=Activity.Status.APPROVED).count()
            source = f"{item.title} · actividad validada el {item.occurred_on.isoformat()}." if item else "Registro de actividades verificadas de la matrícula."
            state = "meets" if current else "does_not_meet"
        elif requirement.field_code == OpportunityRequirement.Field.VALIDATED_SKILL:
            current = skills.count()
            source = "Registro de habilidades validadas de la matrícula."
            state = "meets" if current else "does_not_meet"
        elif requirement.field_code == OpportunityRequirement.Field.APPROVED_COURSE:
            course_grades = [g for g in grades if g.offering.course.code == requirement.course_code]
            if course_grades:
                grade = course_grades[-1]
                current = str(grade.grade_value)
                source = f"{grade.offering.course.name} ({grade.offering.course.code}), nota verificada en {grade.offering.period.code}; aprobación desde {grade.pass_threshold_snapshot}."
                state = "meets" if grade.grade_value >= grade.pass_threshold_snapshot else "does_not_meet"
            else:
                source = f"No hay nota verificada del curso {requirement.course_code} para esta matrícula."
        results.append({
            "id": str(requirement.pk), "label": requirement.display_label,
            "field": requirement.field_code, "operator": requirement.operator,
            "target": str(requirement.target_number) if requirement.target_number is not None else None,
            "value": current, "status": state, "source": source,
        })
    if any(row["status"] == "does_not_meet" for row in results):
        overall = EligibilitySnapshot.Overall.INELIGIBLE
    elif any(row["status"] == "insufficient" for row in results):
        overall = EligibilitySnapshot.Overall.INSUFFICIENT
    else:
        overall = EligibilitySnapshot.Overall.ELIGIBLE
    encoded = json.dumps(results, sort_keys=True, ensure_ascii=False).encode()
    fingerprint = hashlib.sha256(encoded).hexdigest()
    if not persist:
        return SimpleNamespace(overall_status=overall, results=results, computed_at=timezone.now(), input_fingerprint=fingerprint)
    return EligibilitySnapshot.objects.create(
        version=version, enrollment=enrollment, overall_status=overall,
        results=results, input_fingerprint=fingerprint,
    )


@transaction.atomic
def decide_application(*, actor, application_id, decision, reason):
    application = Application.objects.select_for_update().select_related(
        "version__opportunity", "enrollment__career",
    ).get(pk=application_id)
    OpportunityVersion.objects.select_for_update().get(pk=application.version_id)
    if not can_manage_version(actor, application.version):
        raise PermissionDenied("No tienes permiso para revisar esta convocatoria.")
    if decision not in {Application.Status.SELECTED, Application.Status.NOT_SELECTED, Application.Status.IN_REVIEW}:
        raise ValidationError("Decisión inválida.")
    if not reason.strip():
        raise ValidationError("La decisión requiere un motivo.")
    if application.status == Application.Status.WITHDRAWN or (
        application.status in {Application.Status.SELECTED, Application.Status.NOT_SELECTED}
        and decision != Application.Status.IN_REVIEW
    ):
        raise ValidationError("La postulación ya fue resuelta y no admite otra decisión.")
    snapshot = evaluate_eligibility(application.version, application.enrollment)
    if decision == Application.Status.SELECTED:
        selected_count = Application.objects.select_for_update().filter(
            version=application.version, status=Application.Status.SELECTED,
        ).count()
        if selected_count >= application.version.capacity:
            raise ValidationError("El cupo publicado ya fue alcanzado.")
        if snapshot.overall_status != EligibilitySnapshot.Overall.ELIGIBLE:
            raise ValidationError("La elegibilidad cambió o no está completa; no se puede seleccionar hasta revisión humana de los datos.")
    previous = application.status
    application.status = decision
    application.save(update_fields=("status",))
    decision_row = ApplicationDecision.objects.create(
        application=application, actor=actor, previous_status=previous,
        decision=decision, reason=reason.strip(), resolution_eligibility=snapshot,
    )
    record_event(actor=actor, action="opportunity.application_decided", obj=decision_row,
                 scope_type="career", scope_id=application.enrollment.career_id,
                 reason=reason.strip(), safe_metadata={"decision": decision, "previousStatus": previous,
                                                       "opportunityVersion": application.version.version_number})
    opportunity = application.version.opportunity
    if opportunity.status == Opportunity.Status.CLOSED and not Application.objects.filter(
        version__opportunity=opportunity,
        status__in=(Application.Status.SUBMITTED, Application.Status.IN_REVIEW),
    ).exists():
        opportunity.status = Opportunity.Status.RESOLVED
        opportunity.save(update_fields=("status", "updated_at"))
        record_event(actor=actor, action="opportunity.resolved", obj=opportunity,
                     scope_type="career", scope_id=application.enrollment.career_id,
                     reason="Todas las postulaciones recibieron resolución",
                     safe_metadata={"version": application.version.version_number})
    return application
