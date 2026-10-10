from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.audit.services import record_event

from .models import RoleAssignment


def _may_manage_scope(actor, scope, institution_id=None, career_id=None):
    if not actor.is_authenticated or not actor.is_active:
        return False
    if actor.is_superuser:
        return True
    today = timezone.localdate()
    grants = RoleAssignment.objects.filter(
        user=actor, active=True, starts_at__lte=today,
    ).filter(Q(ends_at__isnull=True) | Q(ends_at__gte=today))
    if scope == RoleAssignment.Scope.INSTITUTION:
        return grants.filter(role=RoleAssignment.Role.INSTITUTION_ADMIN, scope="institution", institution_id=institution_id).exists()
    return grants.filter(
        Q(role=RoleAssignment.Role.CAREER_ADMIN, scope="career", career_id=career_id)
        | Q(role=RoleAssignment.Role.INSTITUTION_ADMIN, scope="institution", institution_id=institution_id)
    ).exists()


def grant_role(*, actor, user, role, scope, institution=None, career=None, group=None, starts_at=None, ends_at=None, reason):
    """Grant a scoped role atomically; a person can never grant themselves authority."""
    if actor.pk == user.pk:
        raise PermissionDenied("No puedes concederte roles o ámbitos a ti mismo.")
    if scope == RoleAssignment.Scope.INSTITUTION:
        if not institution or career or group:
            raise ValidationError("El ámbito institucional requiere únicamente una institución.")
        allowed = _may_manage_scope(actor, scope, institution_id=institution.pk)
    elif scope == RoleAssignment.Scope.CAREER:
        if not career or institution or group:
            raise ValidationError("El ámbito de carrera requiere únicamente una carrera.")
        allowed = _may_manage_scope(actor, scope, institution_id=career.institution_id, career_id=career.pk)
    elif scope == RoleAssignment.Scope.GROUP:
        if not group or institution or career:
            raise ValidationError("El ámbito de grupo requiere únicamente un grupo.")
        allowed = _may_manage_scope(actor, RoleAssignment.Scope.CAREER, institution_id=group.course.career.institution_id, career_id=group.course.career_id)
    else:
        raise ValidationError("Ámbito no reconocido.")
    if not allowed:
        raise PermissionDenied("No tienes autorización para administrar roles en este ámbito.")
    if not reason.strip():
        raise ValidationError({"reason": "Registra el motivo de la asignación."})
    assignment = RoleAssignment(
        user=user, role=role, scope=scope, institution=institution, career=career, group=group,
        starts_at=starts_at or timezone.localdate(), ends_at=ends_at, granted_by=actor, reason=reason.strip(),
    )
    assignment.full_clean()
    with transaction.atomic():
        assignment.save()
        record_event(actor=actor, action="role.granted", obj=assignment, scope_type=scope,
                     scope_id=institution.pk if institution else career.pk if career else group.pk,
                     reason=reason.strip(), safe_metadata={"role": role})
    return assignment


def revoke_role(*, actor, assignment, reason):
    if actor.pk == assignment.user_id:
        raise PermissionDenied("No puedes revocar una asignación mediante auto-administración.")
    if not _may_manage_scope(actor, assignment.scope,
                             institution_id=assignment.institution_id or (assignment.career.institution_id if assignment.career_id else assignment.group.course.career.institution_id),
                             career_id=assignment.career_id or (assignment.group.course.career_id if assignment.group_id else None)):
        raise PermissionDenied("No tienes autorización para administrar esta asignación.")
    if not reason.strip():
        raise ValidationError({"reason": "Registra el motivo de la revocación."})
    with transaction.atomic():
        assignment.active = False
        assignment.save(update_fields=("active",))
        record_event(actor=actor, action="role.revoked", obj=assignment, scope_type=assignment.scope,
                     scope_id=assignment.institution_id or assignment.career_id or assignment.group_id,
                     reason=reason.strip(), safe_metadata={"role": assignment.role})
    return assignment
