from .models import AuditEvent


def record_event(*, actor, action, obj, scope_type="", scope_id="", reason="", safe_metadata=None):
    """Persist only allowlisted, non-secret context supplied by the caller."""
    return AuditEvent.objects.create(
        actor=actor,
        action=action,
        object_type=obj._meta.label_lower,
        object_id=str(obj.pk),
        scope_type=scope_type,
        scope_id=str(scope_id) if scope_id else "",
        reason=reason,
        safe_metadata=safe_metadata or {},
    )
