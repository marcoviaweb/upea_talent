"""Record failed state-changing API operations without storing request payloads."""
from django.db import DatabaseError


class FailedOperationAuditMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if (request.path.startswith("/api/v1/") and request.path != "/api/v1/auth/login/"
                and request.method in {"POST", "PUT", "PATCH", "DELETE"} and response.status_code >= 400
                and getattr(request, "user", None) is not None and request.user.is_authenticated):
            try:
                from apps.accounts.permissions import current_role_assignments
                from apps.audit.models import AuditEvent
                assignment = current_role_assignments(request.user).select_related("career", "institution", "group__course__career").first()
                scope_type, scope_id = "", ""
                if assignment:
                    scope_type = assignment.scope
                    scope_id = (assignment.career_id or assignment.institution_id or
                                (assignment.group.course.career_id if assignment.group_id else ""))
                    if assignment.scope == "group" and assignment.group_id:
                        scope_type = "career"
                AuditEvent.objects.create(
                    actor=request.user, action="api.operation_failed", object_type="http.request",
                    object_id=request.path[:80], scope_type=scope_type, scope_id=str(scope_id) if scope_id else "",
                    result="failure", safe_metadata={"httpStatus": response.status_code, "method": request.method},
                )
            except (DatabaseError, AttributeError, TypeError):
                # An unavailable audit store must not replace the original API response.
                pass
        return response
