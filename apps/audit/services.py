from .models import AuditEvent
from django.db.models import Q


def record_event(*, actor, action, obj, scope_type="", scope_id="", reason="", safe_metadata=None):
    """Persist only allowlisted, non-secret context supplied by the caller."""
    from apps.accounts.permissions import current_role_assignments

    roles = current_role_assignments(actor).select_related("career", "institution", "group")
    if scope_type == "career" and scope_id:
        roles = roles.filter(Q(scope="career", career_id=scope_id) | Q(scope="group", group__course__career_id=scope_id))
    elif scope_type == "institution" and scope_id:
        roles = roles.filter(institution_id=scope_id)
    elif scope_type == "group" and scope_id:
        roles = roles.filter(group_id=scope_id)
    role_snapshot = [
        {"role": assignment.role, "scope": assignment.scope,
         "scopeCode": assignment.career.code if assignment.career_id else assignment.institution.short_name if assignment.institution_id else assignment.group.group_code}
        for assignment in roles
    ]
    if actor.is_superuser:
        role_snapshot.append({"role": "superuser", "scope": "global", "scopeCode": "UPEA"})
    metadata = dict(safe_metadata or {})
    metadata["actorRoles"] = role_snapshot
    return AuditEvent.objects.create(
        actor=actor,
        action=action,
        object_type=obj._meta.label_lower,
        object_id=str(obj.pk),
        scope_type=scope_type,
        scope_id=str(scope_id) if scope_id else "",
        reason=reason,
        safe_metadata=metadata,
    )
