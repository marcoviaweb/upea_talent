from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.accounts.models import RoleAssignment
from apps.accounts.permissions import current_role_assignments, visible_course_enrollments
from apps.academics.models import AcademicPeriod, Career, Enrollment, TeachingAssignment
from apps.activities.services import can_manage_spd
from apps.audit.services import record_event
from .models import SupportAction, SupportAlert, SupportCase, SupportRuleVersion
from .services import evaluate_active_rules, manageable_careers, period_indicators


class RuleInput(serializers.Serializer):
    careerId = serializers.UUIDField()
    validFromPeriodId = serializers.UUIDField()
    thresholdPoints = serializers.DecimalField(max_digits=5, decimal_places=2, min_value=1, max_value=100)
    minimumVerifiedCourses = serializers.IntegerField(min_value=2, max_value=30, default=3)


class CaseInput(serializers.Serializer):
    alertId = serializers.UUIDField()
    assignedToId = serializers.IntegerField(required=False, allow_null=True)


class ActionInput(serializers.Serializer):
    kind = serializers.ChoiceField(choices=SupportAction.Kind.choices)
    description = serializers.CharField(max_length=1000, trim_whitespace=True)
    dueDate = serializers.DateField(required=False, allow_null=True)
    status = serializers.ChoiceField(choices=("planned", "in_progress", "completed", "cancelled"), default="planned")


def _manager(user, career):
    return can_manage_spd(user, career)


def _can_receive_case_assignment(user, career):
    if _manager(user, career):
        return True
    today = timezone.localdate()
    assigned_groups = TeachingAssignment.objects.filter(
        user=user, role=TeachingAssignment.AssignmentRole.TEACHER, active=True,
        offering__course__career=career, starts_on__lte=today,
    ).filter(Q(ends_on__isnull=True) | Q(ends_on__gte=today)).values("offering_id")
    return current_role_assignments(user).filter(
        role=RoleAssignment.Role.TEACHER, scope=RoleAssignment.Scope.GROUP,
        group_id__in=assigned_groups,
    ).exists()


def _rule_card(rule):
    return {"id": str(rule.pk), "career": rule.career.name, "careerCode": rule.career.code,
        "validFromPeriod": rule.valid_from.name, "indicator": rule.get_indicator_display(), "indicatorCode": rule.indicator,
        "version": rule.version, "thresholdPoints": str(rule.threshold_points), "minimumVerifiedCourses": rule.minimum_verified_courses,
        "active": rule.active, "createdAt": rule.created_at.isoformat()}


def _alert_card(alert, manager=False):
    student = alert.enrollment.student.user
    case = getattr(alert, "support_case", None)
    return {"id": str(alert.pk), "student": student.get_full_name(), "studentNumber": alert.enrollment.student.student_number,
        "career": alert.enrollment.career.name, "careerCode": alert.enrollment.career.code,
        "period": alert.period.name, "status": alert.status, "statusLabel": alert.get_status_display(),
        "rule": _rule_card(alert.rule), "evidence": alert.evidence_snapshot,
        "case": _case_card(case, manager=manager) if case else None, "isOwn": student.pk == alert.enrollment.student.user_id,
        "createdAt": alert.created_at.isoformat()}


def _case_card(case, manager=False):
    if not case:
        return None
    return {"id": str(case.pk), "status": case.status, "statusLabel": case.get_status_display(),
        "assignedTo": case.assigned_to.get_full_name() if case.assigned_to else "Sin asignar",
        "outcome": case.outcome, "closedAt": case.closed_at.isoformat() if case.closed_at else None,
        "createdAt": case.created_at.isoformat(),
        "actions": [{"id": str(row.pk), "kind": row.get_kind_display(), "kindCode": row.kind,
            "description": row.description, "dueDate": row.due_date.isoformat() if row.due_date else None,
            "status": row.status, "recordedBy": row.recorded_by.get_full_name(),
            "completedAt": row.completed_at.isoformat() if row.completed_at else None,
            "createdAt": row.created_at.isoformat()} for row in case.actions.select_related("recorded_by")]}


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def api_support(request):
    user = request.user
    careers = manageable_careers(user)
    if request.method == "POST":
        data = RuleInput(data=request.data)
        data.is_valid(raise_exception=True)
        values = data.validated_data
        career = Career.objects.filter(pk=values["careerId"]).first()
        period = AcademicPeriod.objects.filter(pk=values["validFromPeriodId"], career=career).first() if career else None
        if not career or not period:
            return Response({"detail": "La carrera o el periodo inicial no es válido."}, status=400)
        if not _manager(user, career):
            return Response({"detail": "No tienes autorización para configurar reglas en esta carrera."}, status=403)
        with transaction.atomic():
            Career.objects.select_for_update().get(pk=career.pk)
            version = (SupportRuleVersion.objects.filter(career=career, indicator=SupportRuleVersion.Indicator.VERIFIED_AVERAGE_DECLINE).order_by("-version").values_list("version", flat=True).first() or 0) + 1
            rule = SupportRuleVersion(career=career, valid_from=period, version=version,
                indicator=SupportRuleVersion.Indicator.VERIFIED_AVERAGE_DECLINE, threshold_points=values["thresholdPoints"],
                minimum_verified_courses=values["minimumVerifiedCourses"], active=True, created_by=user, published_at=timezone.now())
            # Rule versions are immutable; deactivate previous version first, then publish the replacement.
            SupportRuleVersion.objects.filter(career=career, indicator=rule.indicator, active=True).update(active=False)
            rule.save()
            record_event(actor=user, action="support.rule_published", obj=rule, scope_type="career", scope_id=career.pk,
                         reason="Publicación de regla versionada de acompañamiento", safe_metadata={"version": version, "threshold": str(rule.threshold_points)})
        return Response(_rule_card(rule), status=201)

    managed_ids = list(careers.values_list("id", flat=True))
    rules = SupportRuleVersion.objects.filter(career_id__in=managed_ids).select_related("career", "valid_from")
    group_rows = list(visible_course_enrollments(user).values_list(
        "enrollment__student_id", "offering__course__career_id",
    ))
    group_pairs = set(group_rows)
    if user.is_superuser:
        alerts = SupportAlert.objects.all()
    else:
        # Managers see their career; delegated staff see their cases; teachers can
        # discover signals only for students currently enrolled in their own groups.
        alerts = SupportAlert.objects.filter(enrollment__career_id__in=managed_ids) | SupportAlert.objects.filter(support_case__assigned_to=user)
        if group_rows:
            alerts |= SupportAlert.objects.filter(
                enrollment__student_id__in={student_id for student_id, _career_id in group_rows},
                enrollment__career_id__in={career_id for _student_id, career_id in group_rows},
            )
    own_enrollments = Enrollment.objects.filter(student__user=user).select_related("career", "period")
    if own_enrollments.exists():
        alerts = alerts | SupportAlert.objects.filter(enrollment__student__user=user)
    alerts = alerts.distinct().select_related("rule__career", "rule__valid_from", "enrollment__career", "enrollment__student__user", "period").prefetch_related("support_case__actions__recorded_by")
    visible_alerts = []
    for alert in alerts:
        manager = _manager(user, alert.enrollment.career)
        assigned = getattr(getattr(alert, "support_case", None), "assigned_to_id", None) == user.pk
        own = alert.enrollment.student.user_id == user.pk
        group_teacher = (alert.enrollment.student_id, alert.enrollment.career_id) in group_pairs
        if manager or assigned or own or group_teacher:
            payload = _alert_card(alert, manager=manager or assigned)
            if not (manager or assigned or own):
                payload["case"] = None
            visible_alerts.append(payload | {"isAssigned": assigned, "isGroupTeacher": group_teacher})
    own_metrics = []
    for enrollment in own_enrollments:
        own_metrics.append(period_indicators(enrollment))
    managed_indicators = []
    if managed_ids or user.is_superuser:
        managed_enrollments = Enrollment.objects.filter(career_id__in=managed_ids).select_related("student__user", "career", "period")
        for enrollment in managed_enrollments:
            managed_indicators.append({"student": enrollment.student.user.get_full_name(),
                "studentNumber": enrollment.student.student_number, "career": enrollment.career.name,
                **period_indicators(enrollment)})
    rule_rows = [_rule_card(rule) for rule in rules if _manager(user, rule.career)]
    return Response({"canManage": bool(managed_ids) or user.is_superuser,
        "careers": [{"id": str(c.pk), "name": c.name, "code": c.code} for c in careers],
        "periods": [{"id": str(p.pk), "name": p.name, "code": p.code, "careerId": str(p.career_id), "status": p.status}
                    for p in AcademicPeriod.objects.filter(career_id__in=managed_ids).order_by("-starts_on")],
        "rules": rule_rows, "alerts": visible_alerts, "myIndicators": own_metrics,
        "managedIndicators": managed_indicators})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def api_scan(request):
    career = Career.objects.filter(pk=request.data.get("careerId")).first() if request.data.get("careerId") else None
    if request.data.get("careerId") and not career:
        return Response({"detail": "No se encontró la carrera."}, status=404)
    try:
        created = evaluate_active_rules(actor=request.user, career=career)
    except PermissionDenied as exc:
        return Response({"detail": str(exc)}, status=403)
    return Response({"created": len(created), "detail": f"Análisis terminado. Se generaron {len(created)} alertas explicables."})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@transaction.atomic
def api_create_case(request):
    data = CaseInput(data=request.data)
    data.is_valid(raise_exception=True)
    alert = SupportAlert.objects.select_for_update().select_related("enrollment__career").filter(pk=data.validated_data["alertId"]).first()
    if not alert:
        return Response({"detail": "No se encontró la alerta."}, status=404)
    if not _manager(request.user, alert.enrollment.career):
        return Response({"detail": "Solo coordinación autorizada puede abrir un caso."}, status=403)
    if hasattr(alert, "support_case"):
        return Response({"detail": "Esta alerta ya tiene un caso de acompañamiento."}, status=409)
    if alert.status != SupportAlert.Status.OPEN:
        return Response({"detail": "Solo se puede abrir un caso desde una alerta pendiente de revisión."}, status=409)
    assignee_id = data.validated_data.get("assignedToId") or request.user.pk
    assignee = request.user.__class__.objects.filter(pk=assignee_id, is_active=True).first()
    if not assignee or not _can_receive_case_assignment(assignee, alert.enrollment.career):
        return Response({"detail": "El responsable debe ser coordinación o docencia activa en un grupo de la misma carrera."}, status=400)
    case = SupportCase.objects.create(alert=alert, assigned_to=assignee, created_by=request.user)
    alert.status = SupportAlert.Status.CASE_OPEN
    alert.save(update_fields=("status",))
    record_event(actor=request.user, action="support.case_opened", obj=case, scope_type="career", scope_id=alert.enrollment.career_id,
                 reason="Apertura de expediente de acompañamiento", safe_metadata={"assignedTo": assignee.pk})
    return Response(_case_card(case, manager=True), status=201)


def _authorized_case(user, case):
    return user.pk == case.alert.enrollment.student.user_id or _manager(user, case.alert.enrollment.career) or case.assigned_to_id == user.pk


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@transaction.atomic
def api_case_action(request, case_id):
    case = SupportCase.objects.select_for_update().select_related("alert__enrollment__career", "alert__enrollment__student__user").filter(pk=case_id).first()
    if not case:
        return Response({"detail": "No se encontró el caso."}, status=404)
    if not _authorized_case(request.user, case):
        return Response({"detail": "No tienes acceso a este expediente de acompañamiento."}, status=403)
    if case.status in (SupportCase.Status.CLOSED, SupportCase.Status.DISCARDED):
        return Response({"detail": "El expediente ya está cerrado."}, status=409)
    data = ActionInput(data=request.data)
    data.is_valid(raise_exception=True)
    values = data.validated_data
    is_student = request.user.pk == case.alert.enrollment.student.user_id
    if is_student:
        if values["kind"] != SupportAction.Kind.STUDENT_RESPONSE or values["status"] != "completed":
            return Response({"detail": "El estudiante puede registrar su respuesta a la sugerencia."}, status=403)
    elif not (_manager(request.user, case.alert.enrollment.career) or case.assigned_to_id == request.user.pk):
        return Response({"detail": "Solo el responsable asignado o coordinación puede actualizar el caso."}, status=403)
    action = SupportAction.objects.create(case=case, kind=values["kind"], description=values["description"],
        due_date=values.get("dueDate"), status=values["status"], recorded_by=request.user,
        completed_at=timezone.now() if values["status"] == "completed" else None)
    if not is_student and case.status == SupportCase.Status.OPEN:
        case.status = SupportCase.Status.IN_PROGRESS
        case.save(update_fields=("status",))
    record_event(actor=request.user, action="support.action_recorded", obj=action, scope_type="career", scope_id=case.alert.enrollment.career_id,
                 reason="Interacción registrada en expediente restringido", safe_metadata={"kind": action.kind, "status": action.status})
    return Response({"id": str(action.pk), "detail": "Seguimiento registrado."}, status=201)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@transaction.atomic
def api_close_case(request, case_id):
    case = SupportCase.objects.select_for_update().select_related("alert__enrollment__career", "alert__enrollment__student__user").filter(pk=case_id).first()
    if not case:
        return Response({"detail": "No se encontró el caso."}, status=404)
    if not (_manager(request.user, case.alert.enrollment.career) or case.assigned_to_id == request.user.pk):
        return Response({"detail": "Solo coordinación autorizada o el responsable asignado puede cerrar el caso."}, status=403)
    if case.status in (SupportCase.Status.CLOSED, SupportCase.Status.DISCARDED):
        return Response({"detail": "El expediente ya está cerrado."}, status=409)
    outcome = str(request.data.get("outcome", "")).strip()
    if len(outcome) < 10 or len(outcome) > 1000:
        return Response({"detail": "Registra un resultado de cierre de entre 10 y 1000 caracteres."}, status=400)
    case.status = SupportCase.Status.CLOSED
    case.outcome = outcome
    case.closed_at = timezone.now()
    case.save(update_fields=("status", "outcome", "closed_at"))
    case.alert.status = SupportAlert.Status.RESOLVED
    case.alert.save(update_fields=("status",))
    record_event(actor=request.user, action="support.case_closed", obj=case, scope_type="career", scope_id=case.alert.enrollment.career_id,
                 reason="Cierre del expediente con resultado", safe_metadata={"status": case.status})
    return Response({"detail": "Caso cerrado con resultado."})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@transaction.atomic
def api_discard_case(request, case_id):
    case = SupportCase.objects.select_for_update().select_related("alert__enrollment__career").filter(pk=case_id).first()
    if not case:
        return Response({"detail": "No se encontró el caso."}, status=404)
    if not (_manager(request.user, case.alert.enrollment.career) or case.assigned_to_id == request.user.pk):
        return Response({"detail": "Solo coordinación autorizada o el responsable asignado puede descartar el caso."}, status=403)
    reason = str(request.data.get("reason", "")).strip()
    if len(reason) < 10 or len(reason) > 1000:
        return Response({"detail": "Registra un motivo de descarte de entre 10 y 1000 caracteres."}, status=400)
    if case.status in (SupportCase.Status.CLOSED, SupportCase.Status.DISCARDED):
        return Response({"detail": "El expediente ya está cerrado."}, status=409)
    case.status = SupportCase.Status.DISCARDED
    case.outcome = reason
    case.closed_at = timezone.now()
    case.save(update_fields=("status", "outcome", "closed_at"))
    case.alert.status = SupportAlert.Status.DISMISSED
    case.alert.save(update_fields=("status",))
    record_event(actor=request.user, action="support.case_discarded", obj=case, scope_type="career", scope_id=case.alert.enrollment.career_id,
                 reason="Descarte motivado del expediente", safe_metadata={"status": case.status})
    return Response({"detail": "Caso descartado con motivo registrado."})
