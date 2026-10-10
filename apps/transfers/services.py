from datetime import datetime, time

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.accounts.models import RoleAssignment
from apps.accounts.permissions import current_role_assignments
from apps.activities.models import Activity, PointsMovement
from apps.activities.services import can_manage_spd, can_review
from apps.audit.services import record_event
from apps.academics.models import Enrollment
from .models import TransferAdjustment, TransferAllocation, TransferMovement, TransferRequest, TransferReview, TransferRiskAlert


PENDING_STATES = (TransferRequest.Status.IN_REVIEW, TransferRequest.Status.FLAGGED)
RESERVING_STATES = (*PENDING_STATES, TransferRequest.Status.APPROVED)
MAX_PER_REQUEST = 10
MAX_PER_MONTH = 20


def _month_window(value=None):
    local_day = value or timezone.localdate()
    start_local = local_day.replace(day=1)
    year, month = local_day.year, local_day.month
    if month == 12:
        end_local = start_local.replace(year=year + 1, month=1)
    else:
        end_local = start_local.replace(month=month + 1)
    zone = timezone.get_current_timezone()
    return timezone.make_aware(datetime.combine(start_local, time.min), zone), timezone.make_aware(datetime.combine(end_local, time.min), zone)


def _source_available(movement, *, exclude_request_id=None):
    if movement.points <= 0 or movement.activity_id is None or movement.category.transferable is False:
        return 0
    if movement.reversal_of_id or PointsMovement.objects.filter(reversal_of_id=movement.pk).exists():
        return 0
    if movement.activity.status != Activity.Status.APPROVED:
        return 0
    sent = TransferMovement.objects.filter(source_movement=movement, side=TransferMovement.Side.DEBIT).aggregate(total=Sum("points"))["total"] or 0
    reservations = TransferAllocation.objects.filter(source_movement=movement, request__status__in=PENDING_STATES)
    if exclude_request_id:
        reservations = reservations.exclude(request_id=exclude_request_id)
    held = reservations.aggregate(total=Sum("amount"))["total"] or 0
    return max(0, movement.points + sent - held)


def transferable_sources(enrollment):
    rows = PointsMovement.objects.filter(
        enrollment=enrollment, points__gt=0, activity__status=Activity.Status.APPROVED,
        category__transferable=True, reversal_of__isnull=True,
    ).select_related("activity", "category", "regulation").order_by("created_at", "pk")
    result = []
    for row in rows:
        available = _source_available(row)
        if available:
            result.append({"movement": row, "available": available})
    return result


def _monthly_reserved(sender, start, end):
    return TransferRequest.objects.filter(
        sender__student_id=sender.student_id,
        submitted_at__gte=start, submitted_at__lt=end,
        status__in=RESERVING_STATES,
    ).aggregate(total=Sum("amount"))["total"] or 0


def _risk_flags(sender, recipient, activity, now):
    flags = []
    start, end = _month_window(now.astimezone(timezone.get_current_timezone()).date())
    repeated = TransferRequest.objects.filter(
        sender__student_id=sender.student_id, recipient__student_id=recipient.student_id,
        submitted_at__gte=start, submitted_at__lt=end,
        status__in=RESERVING_STATES,
    ).exclude(activity=activity).exists()
    if repeated:
        flags.append("repeated_recipient_month")
    reciprocal = TransferRequest.objects.filter(
        sender__student_id=recipient.student_id, recipient__student_id=sender.student_id,
        submitted_at__gte=start, submitted_at__lt=end,
        status__in=RESERVING_STATES,
    ).exists()
    if reciprocal:
        flags.append("reciprocal_pattern")
    return flags


@transaction.atomic
def create_transfer_request(*, actor, sender_id, recipient_id, activity_id, amount, reason, idempotency_key):
    sender = Enrollment.objects.select_related("student", "career", "period").get(pk=sender_id, student__user=actor)
    if sender.status != Enrollment.Status.ACTIVE:
        raise ValidationError("Solo puedes transferir puntos desde una matrícula activa.")
    # The profile lock serializes quota checks across concurrent sessions and career enrollments.
    sender.student.__class__.objects.select_for_update().get(pk=sender.student_id)
    if TransferRiskAlert.objects.filter(
        request__sender__student_id=sender.student_id, status=TransferRiskAlert.Status.OPEN,
        code="origin_revoked_after_transfer",
    ).exists():
        raise ValidationError("La cuenta tiene una revisión pendiente por puntos ya transferidos desde un mérito revocado.")
    try:
        amount = int(amount)
    except (ValueError, TypeError):
        raise ValidationError("El monto debe ser un número entero.")
    if amount < 1 or amount > MAX_PER_REQUEST:
        raise ValidationError(f"Cada solicitud debe ser de 1 a {MAX_PER_REQUEST} puntos.")
    reason = str(reason or "").strip()
    idempotency_key = str(idempotency_key or "").strip()
    if not idempotency_key or len(idempotency_key) > 64:
        raise ValidationError("No se recibió una clave de solicitud válida; vuelve a enviar el formulario.")
    recipient = Enrollment.objects.select_related("student", "career").get(pk=recipient_id, status=Enrollment.Status.ACTIVE)
    if sender.student_id == recipient.student_id:
        raise ValidationError("No puedes enviarte puntos a ti mismo.")
    if sender.career_id != recipient.career_id:
        raise ValidationError("El emisor y el receptor deben pertenecer a la misma carrera.")
    old = TransferRequest.objects.filter(sender=sender, idempotency_key=idempotency_key).first()
    if old:
        if (old.recipient_id, old.activity_id, old.amount, old.reason) != (recipient.pk, activity_id, amount, reason):
            raise ValidationError("La clave de reintento ya fue usada para una solicitud diferente.")
        return old, False
    if TransferRequest.objects.filter(sender=sender, recipient=recipient, activity_id=activity_id).exclude(
        status__in=(TransferRequest.Status.REJECTED, TransferRequest.Status.CANCELLED),
    ).exists():
        raise ValidationError("Ya existe una solicitud activa para reconocer esta colaboración a esa persona.")
    activity = Activity.objects.select_for_update().select_related("enrollment", "category", "category__regulation").get(pk=activity_id)
    if activity.enrollment_id != sender.pk or activity.enrollment.student_id != sender.student_id:
        raise ValidationError("Selecciona una actividad de colaboración validada de tu matrícula.")
    if activity.status != Activity.Status.APPROVED or not activity.category.transferable:
        raise ValidationError("Solo se pueden transferir puntos de una colaboración aprobada y marcada como transferible.")
    origin = PointsMovement.objects.select_for_update().filter(
        activity=activity, points__gt=0, reversal_of__isnull=True,
    ).select_related("category", "regulation", "activity").first()
    if not origin or not origin.category.transferable:
        raise ValidationError("Esta actividad no tiene un movimiento SPD transferible.")
    if _source_available(origin) < amount:
        raise ValidationError("El saldo transferible disponible en esta actividad no alcanza el monto solicitado.")
    now = timezone.now()
    month_start, month_end = _month_window(now.astimezone(timezone.get_current_timezone()).date())
    if _monthly_reserved(sender, month_start, month_end) + amount > MAX_PER_MONTH:
        raise ValidationError(f"El límite es {MAX_PER_MONTH} puntos enviados por persona y mes calendario.")
    risk_flags = _risk_flags(sender, recipient, activity, now)
    request = TransferRequest.objects.create(
        sender=sender, recipient=recipient, activity=activity, amount=amount, reason=reason,
        idempotency_key=idempotency_key,
        status=TransferRequest.Status.FLAGGED if risk_flags else TransferRequest.Status.IN_REVIEW,
        risk_flags=risk_flags,
    )
    TransferAllocation.objects.create(request=request, source_movement=origin, amount=amount)
    for flag in risk_flags:
        descriptions = {
            "repeated_recipient_month": "Varias solicitudes del mismo emisor al mismo estudiante durante el mes.",
            "reciprocal_pattern": "Se detectó un patrón de transferencias entre las mismas dos personas.",
        }
        TransferRiskAlert.objects.create(request=request, code=flag, description=descriptions[flag])
    record_event(actor=actor, action="transfer.submitted", obj=request, scope_type="career", scope_id=sender.career_id,
                 reason=reason, safe_metadata={"amount": amount, "status": request.status, "riskFlags": risk_flags})
    return request, True


def can_review_transfer(actor, request):
    if actor.pk in {request.sender.student.user_id, request.recipient.student.user_id}:
        return False
    return can_manage_spd(actor, request.sender.career) or can_review(actor, request.activity)


@transaction.atomic
def review_transfer(*, actor, request_id, decision, reason):
    request = TransferRequest.objects.select_for_update().select_related(
        "sender__student__user", "sender__career", "recipient__student__user", "activity__category__regulation",
    ).get(pk=request_id)
    if not can_review_transfer(actor, request):
        raise PermissionDenied("No tienes autorización independiente para revisar esta transferencia.")
    if decision not in {"approve", "reject"} or len(str(reason or "").strip()) < 5:
        raise ValidationError("Elige aprobar o rechazar e indica un motivo de al menos cinco caracteres.")
    if request.status not in PENDING_STATES:
        raise ValidationError("La solicitud ya fue resuelta o cancelada.")
    reason = str(reason).strip()
    allocations = list(request.allocations.select_related("source_movement__activity", "source_movement__category"))
    if decision == "approve":
        request.sender.student.__class__.objects.select_for_update().get(pk=request.sender.student_id)
        month_start, month_end = _month_window(request.submitted_at.astimezone(timezone.get_current_timezone()).date())
        if _monthly_reserved(request.sender, month_start, month_end) > MAX_PER_MONTH:
            raise ValidationError("El límite mensual cambió; esta transferencia requiere regularización administrativa.")
        for allocation in allocations:
            origin = PointsMovement.objects.select_for_update(of=("self",)).select_related("activity", "category").get(pk=allocation.source_movement_id)
            if _source_available(origin, exclude_request_id=request.pk) < allocation.amount:
                raise ValidationError("El saldo del mérito de origen cambió; no se puede aprobar esta solicitud.")
            if origin.category.transferable is False or origin.activity.status != Activity.Status.APPROVED:
                raise ValidationError("El mérito de origen ya no es transferible.")
        for allocation in allocations:
            TransferMovement.objects.create(
                request=request, source_movement=allocation.source_movement, enrollment=request.sender,
                side=TransferMovement.Side.DEBIT, points=-allocation.amount,
            )
            TransferMovement.objects.create(
                request=request, source_movement=allocation.source_movement, enrollment=request.recipient,
                side=TransferMovement.Side.CREDIT, points=allocation.amount,
            )
        request.status = TransferRequest.Status.APPROVED
    else:
        request.status = TransferRequest.Status.REJECTED
    request.resolved_by = actor
    request.resolved_at = timezone.now()
    request.save(update_fields=("status", "resolved_by", "resolved_at"))
    TransferReview.objects.create(request=request, reviewer=actor, decision=decision, reason=reason)
    record_event(actor=actor, action=f"transfer.{decision}d" if decision == "approve" else "transfer.rejected", obj=request,
                 scope_type="career", scope_id=request.sender.career_id, reason=reason,
                 safe_metadata={"amount": request.amount, "senderEnrollment": str(request.sender_id), "recipientEnrollment": str(request.recipient_id)})
    return request


@transaction.atomic
def cancel_transfer_request(*, actor, request_id):
    request = TransferRequest.objects.select_for_update().select_related("sender__student").get(pk=request_id)
    if request.sender.student.user_id != actor.pk:
        raise PermissionDenied("No puedes cancelar una solicitud ajena.")
    if request.status not in PENDING_STATES:
        raise ValidationError("Solo puedes cancelar una solicitud aún pendiente de revisión.")
    request.status = TransferRequest.Status.CANCELLED
    request.save(update_fields=("status",))
    record_event(actor=actor, action="transfer.cancelled", obj=request, scope_type="career", scope_id=request.sender.career_id,
                 reason="Cancelación solicitada por el emisor", safe_metadata={"amount": request.amount})
    return request


@transaction.atomic
def resolve_risk_alert(*, actor, alert_id, reason):
    alert = TransferRiskAlert.objects.select_for_update().select_related("request__sender__career").get(pk=alert_id)
    if not can_manage_spd(actor, alert.request.sender.career):
        raise PermissionDenied("Solo coordinación o administración de la carrera puede resolver la alerta.")
    reason = str(reason or "").strip()
    if len(reason) < 10:
        raise ValidationError("Documenta la revisión en al menos diez caracteres.")
    if alert.status != TransferRiskAlert.Status.OPEN:
        raise ValidationError("La alerta ya fue resuelta.")
    alert.status = TransferRiskAlert.Status.RESOLVED
    alert.resolved_by = actor
    alert.resolution_reason = reason
    alert.resolved_at = timezone.now()
    alert.save(update_fields=("status", "resolved_by", "resolution_reason", "resolved_at"))
    adjustments = 0
    if alert.code == "origin_revoked_after_transfer":
        original_rows = alert.request.movements.select_related("enrollment").all()
        for movement in original_rows:
            if TransferAdjustment.objects.filter(original_movement=movement).exists():
                continue
            TransferAdjustment.objects.create(
                alert=alert, original_movement=movement, enrollment=movement.enrollment,
                actor=actor, points=-movement.points,
                reason=f"Regularización por revocación del mérito de origen: {reason}"[:500],
            )
            adjustments += 1
    record_event(actor=actor, action="transfer.risk_resolved", obj=alert, scope_type="career", scope_id=alert.request.sender.career_id,
                 reason=reason, safe_metadata={"code": alert.code, "requestId": str(alert.request_id), "compensatingMovements": adjustments})
    return alert
