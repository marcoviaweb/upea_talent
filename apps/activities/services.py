from datetime import date

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import RoleAssignment
from apps.accounts.permissions import current_role_assignments, visible_course_enrollments
from apps.audit.models import AuditEvent
from apps.audit.services import record_event
from .models import Activity, ActivityCategory, EvidenceFile, PointsMovement, Regulation, ReviewDecision


def current_regulation(career, on_date=None):
    on_date = on_date or timezone.localdate()
    return Regulation.objects.filter(career=career, published=True, effective_from__lte=on_date).filter(
        models_q_end(on_date)
    ).order_by("-version").first()


def models_q_end(on_date):
    from django.db.models import Q
    return Q(effective_to__isnull=True) | Q(effective_to__gte=on_date)


def can_review(user, activity):
    allowed_roles = activity.category.reviewer_roles
    if allowed_roles and not current_role_assignments(user).filter(role__in=allowed_roles).exists():
        return False
    if activity.assigned_group_id:
        return visible_course_enrollments(user).filter(enrollment=activity.enrollment, offering_id=activity.assigned_group_id).exists()
    return visible_course_enrollments(user).filter(enrollment=activity.enrollment).exists()


@transaction.atomic
def submit_activity(*, user, enrollment, category, title, description, occurred_on, source, uploaded_file, course_enrollment=None):
    if enrollment.student.user_id != user.pk or enrollment.status != "active":
        raise PermissionDenied("Solo puedes presentar evidencias para tu matrícula activa.")
    if category.regulation.career_id != enrollment.career_id or not category.active or current_regulation(enrollment.career) != category.regulation:
        raise ValidationError("La categoría no está disponible para esta carrera.")
    if course_enrollment and (course_enrollment.enrollment_id != enrollment.pk or not course_enrollment.active):
        raise ValidationError("El grupo no corresponde a tu matrícula activa.")
    if Activity.objects.filter(enrollment=enrollment, occurred_on=occurred_on, title__iexact=title.strip()).exclude(status=Activity.Status.REJECTED).exists():
        raise ValidationError("Ya existe una evidencia activa para esta actividad y fecha; consulta su historial.")
    activity = Activity.objects.create(enrollment=enrollment, category=category, title=title.strip(), description=description.strip(), occurred_on=occurred_on, source=source.strip(), created_by=user, assigned_group=course_enrollment.offering if course_enrollment else None)
    EvidenceFile.objects.create(activity=activity, file=uploaded_file, original_name=uploaded_file.name, content_type=getattr(uploaded_file, "content_type", "application/octet-stream"), size=uploaded_file.size, uploaded_by=user)
    record_event(actor=user, action="evidence.submitted", obj=activity, scope_type="career", scope_id=enrollment.career_id, reason="Presentación de evidencia", safe_metadata={"category": category.code, "fileCount": 1})
    return activity


@transaction.atomic
def review_activity(*, actor, activity, outcome, note):
    activity = Activity.objects.select_for_update().select_related("enrollment", "category__regulation").get(pk=activity.pk)
    if not can_review(actor, activity):
        raise PermissionDenied("No tienes autorización para revisar esta evidencia.")
    allowed = {Activity.Status.IN_REVIEW: {"approve", "observe", "reject"}, Activity.Status.OBSERVED: {"approve", "observe", "reject"}}
    if outcome not in allowed.get(activity.status, set()):
        raise ValidationError("La evidencia no admite esta decisión en su estado actual.")
    if outcome in {"observe", "reject"} and not note.strip():
        raise ValidationError("Registra un motivo o la información que debe corregirse.")
    ReviewDecision.objects.create(activity=activity, reviewer=actor, outcome=outcome, note=note.strip())
    activity.reviewed_by, activity.reviewed_at = actor, timezone.now()
    if outcome == "approve":
        activity.status = Activity.Status.APPROVED
        category = activity.category
        award_exists = PointsMovement.objects.filter(activity=activity, reversal_of__isnull=True).exists()
        if category.active and category.points > 0 and not award_exists:
            PointsMovement.objects.create(enrollment=activity.enrollment, activity=activity, regulation=category.regulation, category=category, actor=actor, points=category.points, reason=f"Evidencia aprobada: {activity.title}")
    else:
        activity.status = Activity.Status.OBSERVED if outcome == "observe" else Activity.Status.REJECTED
    activity.save(update_fields=("status", "reviewed_by", "reviewed_at", "updated_at"))
    record_event(actor=actor, action=f"evidence.{outcome}", obj=activity, scope_type="career", scope_id=activity.enrollment.career_id, reason=note.strip() or "Validación de evidencia", safe_metadata={"status": activity.status})
    return activity


@transaction.atomic
def can_revoke(user, activity):
    return can_manage_spd(user, activity.enrollment.career)


def can_manage_spd(user, career):
    if user.is_superuser:
        return True
    roles = current_role_assignments(user)
    authorized = roles.filter(role=RoleAssignment.Role.INSTITUTION_ADMIN, scope=RoleAssignment.Scope.INSTITUTION, institution_id=career.institution_id).exists()
    authorized |= roles.filter(role__in=(RoleAssignment.Role.CAREER_ADMIN, RoleAssignment.Role.COORDINATOR), scope=RoleAssignment.Scope.CAREER, career_id=career.pk).exists()
    return authorized


@transaction.atomic
def record_verified_activity(*, actor, enrollment, category, title, description, occurred_on, source):
    if enrollment.status != "active" or not can_manage_spd(actor, enrollment.career):
        raise PermissionDenied("No tienes autorización para registrar méritos en esta carrera.")
    if category.regulation.career_id != enrollment.career_id or not category.active or current_regulation(enrollment.career) != category.regulation:
        raise ValidationError("La categoría no está disponible para esta carrera.")
    if not source.strip():
        raise ValidationError("Indica la fuente documental de la verificación.")
    if Activity.objects.filter(enrollment=enrollment, occurred_on=occurred_on, title__iexact=title.strip()).exclude(status=Activity.Status.REJECTED).exists():
        raise ValidationError("Ya existe un registro activo para esta actividad y fecha.")
    activity = Activity.objects.create(enrollment=enrollment, category=category, title=title.strip(), description=description.strip(), occurred_on=occurred_on, source=source.strip(), created_by=actor, status=Activity.Status.APPROVED, reviewed_by=actor, reviewed_at=timezone.now())
    ReviewDecision.objects.create(activity=activity, reviewer=actor, outcome="approve", note=f"Registro administrativo verificado: {source.strip()}"[:500])
    if category.active and category.points > 0:
        PointsMovement.objects.create(enrollment=enrollment, activity=activity, regulation=category.regulation, category=category, actor=actor, points=category.points, reason=f"Actividad verificada por administración: {activity.title}")
    record_event(actor=actor, action="evidence.admin_recorded", obj=activity, scope_type="career", scope_id=enrollment.career_id, reason=f"Registro verificado según fuente: {source.strip()}"[:300], safe_metadata={"category": category.code, "points": category.points})
    return activity


def revoke_activity(*, actor, activity, reason):
    activity = Activity.objects.select_for_update().select_related("enrollment__career__institution", "category__regulation").get(pk=activity.pk)
    if not can_revoke(actor, activity):
        raise PermissionDenied("La revocación requiere un administrador institucional autorizado.")
    if activity.status != Activity.Status.APPROVED or not reason.strip():
        raise ValidationError("Solo se revocan actividades aprobadas y se requiere motivo.")
    original = PointsMovement.objects.filter(activity=activity, reversal_of__isnull=True).first()
    if original and not hasattr(original, "reversal"):
        PointsMovement.objects.create(enrollment=original.enrollment, activity=activity, regulation=original.regulation, category=original.category, actor=actor, points=-original.points, reason=f"Reversión: {reason.strip()}", reversal_of=original)
    ReviewDecision.objects.create(activity=activity, reviewer=actor, outcome="revoke", note=reason.strip())
    activity.status = Activity.Status.REVOKED
    activity.reviewed_by, activity.reviewed_at = actor, timezone.now()
    activity.save(update_fields=("status", "reviewed_by", "reviewed_at", "updated_at"))
    record_event(actor=actor, action="evidence.revoked", obj=activity, scope_type="career", scope_id=activity.enrollment.career_id, reason=reason.strip(), safe_metadata={"reversedPoints": original.points if original and hasattr(original, "reversal") else 0})
    return activity


@transaction.atomic
def resubmit_activity(*, actor, activity, uploaded_file):
    activity = Activity.objects.select_for_update().select_related("enrollment").get(pk=activity.pk)
    if activity.enrollment.student.user_id != actor.pk or activity.status != Activity.Status.OBSERVED:
        raise PermissionDenied("Solo puedes reenviar una evidencia observada de tu matrícula.")
    last_version = activity.files.order_by("-version").values_list("version", flat=True).first() or 0
    EvidenceFile.objects.create(activity=activity, file=uploaded_file, original_name=uploaded_file.name, content_type=getattr(uploaded_file, "content_type", "application/octet-stream"), size=uploaded_file.size, version=last_version + 1, uploaded_by=actor)
    activity.status = Activity.Status.IN_REVIEW
    activity.reviewed_by = None
    activity.reviewed_at = None
    activity.save(update_fields=("status", "reviewed_by", "reviewed_at", "updated_at"))
    record_event(actor=actor, action="evidence.resubmitted", obj=activity, scope_type="career", scope_id=activity.enrollment.career_id, reason="Reenvío con nueva versión de evidencia", safe_metadata={"fileVersion": last_version + 1})
    return activity


def seed_regulation(*, career, actor):
    today = date.today()
    regulation, created = Regulation.objects.get_or_create(career=career, version=1, defaults={"title": "Reglamento SPD de demostración · v1", "effective_from": date(2026, 1, 1), "published": False, "created_by": actor})
    rows = [
        ("approved_course", "Aprobar una materia", "Nota verificada de aprobación registrada por personal autorizado.", 10),
        ("improved_performance", "Mejorar rendimiento", "Comparación verificada con el periodo anterior.", 15),
        ("certified_course", "Curso certificado", "Certificado legible y verificable que indique entidad y fecha.", 10),
        ("seminar", "Seminario o conferencia", "Constancia de participación con evento, organizador y fecha.", 5),
        ("academic_project", "Proyecto académico", "Producto académico y participación individual verificables.", 20),
        ("featured_project", "Proyecto destacado", "Distinción formal emitida por una instancia identificable.", 30),
        ("research", "Participación en investigación", "Constancia del proyecto e identificación del responsable.", 25),
        ("contest", "Participación en concurso", "Constancia de participación emitida por organizadores.", 15),
        ("contest_winner", "Ganador de concurso", "Certificado o acta oficial que acredite el resultado.", 40),
        ("collaboration", "Colaboración validada", "Aporte documentado y validado por responsable del proyecto.", 5),
        ("mentoring", "Mentoría a otro estudiante", "Registro de mentoría confirmada por ambas partes y responsable.", 10),
    ]
    for code, name, criterion, points in rows:
        ActivityCategory.objects.get_or_create(regulation=regulation, code=code, defaults={"name": name, "criterion": criterion, "points": points, "transferable": code in {"collaboration", "mentoring"}, "reviewer_roles": ["teacher", "evidence_reviewer", "coordinator", "career_admin"], "active": True})
    if not regulation.published:
        regulation.published = True
        regulation.published_by = actor
        regulation.published_at = timezone.now()
        regulation.save(update_fields=("published", "published_by", "published_at"))
        record_event(actor=actor, action="spd.regulation_published", obj=regulation, scope_type="career", scope_id=career.pk, reason="Publicación del reglamento ficticio inicial", safe_metadata={"version": regulation.version})
    elif not AuditEvent.objects.filter(action="spd.regulation_published", object_type="activities.regulation", object_id=str(regulation.pk)).exists():
        record_event(actor=regulation.published_by or actor, action="spd.regulation_published", obj=regulation, scope_type="career", scope_id=career.pk, reason="Registro de publicación del reglamento ficticio inicial", safe_metadata={"version": regulation.version})
    return regulation
