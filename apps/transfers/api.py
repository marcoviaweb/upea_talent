from django.core.exceptions import ObjectDoesNotExist
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.accounts.models import RoleAssignment
from apps.accounts.permissions import current_role_assignments, visible_course_enrollments
from apps.academics.models import Enrollment
from apps.activities.models import PointsMovement
from apps.activities.services import can_manage_spd
from apps.transfers.services import _month_window, _monthly_reserved
from .models import TransferAdjustment, TransferMovement, TransferRequest, TransferRiskAlert
from .services import (
    PENDING_STATES, MAX_PER_MONTH, MAX_PER_REQUEST, can_review_transfer,
    cancel_transfer_request, create_transfer_request, resolve_risk_alert,
    review_transfer, transferable_sources,
)


class RequestSerializer(serializers.Serializer):
    senderEnrollment = serializers.UUIDField()
    recipientEnrollment = serializers.UUIDField()
    activity = serializers.UUIDField()
    amount = serializers.IntegerField(min_value=1, max_value=MAX_PER_REQUEST)
    reason = serializers.CharField(max_length=500, min_length=10)
    idempotencyKey = serializers.CharField(max_length=64)


class ReviewSerializer(serializers.Serializer):
    decision = serializers.ChoiceField(choices=("approve", "reject"))
    reason = serializers.CharField(max_length=500, min_length=5)


def _enrollment_payload(enrollment):
    return {
        "id": str(enrollment.pk),
        "student": enrollment.student.user.get_full_name() or enrollment.student.user.username,
        "studentNumber": enrollment.student.student_number,
        "career": enrollment.career.name,
        "careerCode": enrollment.career.code,
        "period": enrollment.period.name,
        "periodCode": enrollment.period.code,
    }


def _request_payload(request, actor):
    latest = request.reviews.select_related("reviewer").order_by("-decided_at").first()
    is_party = request.sender.student.user_id == actor.pk or request.recipient.student.user_id == actor.pk
    reviewer = can_review_transfer(actor, request)
    visible_status = "in_review" if is_party and request.status == TransferRequest.Status.FLAGGED else request.status
    return {
        "id": str(request.pk), "amount": request.amount, "reason": request.reason,
        "status": visible_status, "statusLabel": "En revisión" if is_party and request.status == TransferRequest.Status.FLAGGED else request.get_status_display(),
        "riskFlags": [] if is_party else request.risk_flags, "submittedAt": request.submitted_at.isoformat(),
        "sender": _enrollment_payload(request.sender), "recipient": _enrollment_payload(request.recipient),
        "activity": request.activity.title, "category": request.activity.category.name,
        "isSender": request.sender.student.user_id == actor.pk,
        "canCancel": request.sender.student.user_id == actor.pk and request.status in PENDING_STATES,
        "canReview": request.status in PENDING_STATES and reviewer,
        "review": {"decision": latest.decision, "reason": latest.reason,
                   "reviewer": latest.reviewer.get_full_name() or latest.reviewer.username,
                   "at": latest.decided_at.isoformat()} if latest else None,
        "riskAlerts": [{"id": str(alert.pk), "code": alert.code, "description": alert.description,
                        "status": alert.status, "resolutionReason": alert.resolution_reason}
                       for alert in request.risk_alerts.all()] if reviewer and not is_party else [],
        "adjustments": [{"id": str(row.pk), "points": row.points, "reason": row.reason,
                         "enrollment": str(row.enrollment_id), "createdAt": row.created_at.isoformat()}
                        for row in TransferAdjustment.objects.filter(alert__request=request).select_related("enrollment")],
    }


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def api_transfers(request):
    if request.method == "POST":
        serializer = RequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        try:
            transfer, created = create_transfer_request(
                actor=request.user, sender_id=values["senderEnrollment"],
                recipient_id=values["recipientEnrollment"], activity_id=values["activity"],
                amount=values["amount"], reason=values["reason"], idempotency_key=values["idempotencyKey"],
            )
        except PermissionDenied as exc:
            return Response({"detail": str(exc)}, status=403)
        except ValidationError as exc:
            return Response({"detail": " ".join(exc.messages)}, status=400)
        except ObjectDoesNotExist:
            return Response({"detail": "No se encontró una matrícula o mérito autorizado para esta operación."}, status=404)
        transfer = TransferRequest.objects.select_related(
            "sender__student__user", "sender__career", "sender__period",
            "recipient__student__user", "recipient__career", "recipient__period",
            "activity__category",
        ).prefetch_related("reviews__reviewer", "risk_alerts").get(pk=transfer.pk)
        return Response(_request_payload(transfer, request.user), status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

    own = Enrollment.objects.filter(student__user=request.user)
    enrollments = list(own.filter(status=Enrollment.Status.ACTIVE).select_related("student__user", "career", "period"))
    own_career_ids = {row.career_id for row in enrollments}
    recipients = Enrollment.objects.filter(status=Enrollment.Status.ACTIVE, career_id__in=own_career_ids).exclude(
        student__user=request.user,
    ).select_related("student__user", "career", "period").order_by("career__code", "student__student_number")
    sources = []
    for enrollment in enrollments:
        for entry in transferable_sources(enrollment):
            movement = entry["movement"]
            sources.append({"id": str(movement.activity_id), "enrollment": str(enrollment.pk),
                            "title": movement.activity.title, "category": movement.category.name,
                            "points": movement.points, "available": entry["available"],
                            "date": movement.created_at.isoformat()})
    transfers = TransferRequest.objects.filter(
        Q(sender__student__user=request.user) | Q(recipient__student__user=request.user),
    ).select_related(
        "sender__student__user", "sender__career", "sender__period",
        "recipient__student__user", "recipient__career", "recipient__period", "activity__category",
    ).prefetch_related("reviews__reviewer", "risk_alerts")
    request_payloads = [_request_payload(row, request.user) for row in transfers]
    roles = current_role_assignments(request.user)
    manager_career_ids = roles.filter(
        role__in=(RoleAssignment.Role.CAREER_ADMIN, RoleAssignment.Role.COORDINATOR),
        scope=RoleAssignment.Scope.CAREER,
    ).values("career_id")
    manager_institution_ids = roles.filter(
        role=RoleAssignment.Role.INSTITUTION_ADMIN, scope=RoleAssignment.Scope.INSTITUTION,
    ).values("institution_id")
    reviewable_enrollment_ids = visible_course_enrollments(request.user).values("enrollment_id")
    candidate_reviews = TransferRequest.objects.filter(status__in=PENDING_STATES).filter(
        Q(sender__career_id__in=manager_career_ids)
        | Q(sender__career__institution_id__in=manager_institution_ids)
        | Q(activity__enrollment_id__in=reviewable_enrollment_ids)
    ).distinct().select_related(
        "sender__student__user", "sender__career", "sender__period",
        "recipient__student__user", "recipient__career", "recipient__period", "activity__category",
    ).prefetch_related("reviews__reviewer", "risk_alerts")
    review_queue = [_request_payload(row, request.user) for row in candidate_reviews if can_review_transfer(request.user, row)]
    allowed_review_careers = current_role_assignments(request.user).filter(
        role__in=(RoleAssignment.Role.CAREER_ADMIN, RoleAssignment.Role.COORDINATOR),
        scope=RoleAssignment.Scope.CAREER,
    ).values_list("career_id", flat=True)
    if not request.user.is_superuser:
        institution_ids = current_role_assignments(request.user).filter(
            role=RoleAssignment.Role.INSTITUTION_ADMIN, scope=RoleAssignment.Scope.INSTITUTION,
        ).values_list("institution_id", flat=True)
        alerts = TransferRiskAlert.objects.filter(
            Q(request__sender__career_id__in=allowed_review_careers)
            | Q(request__sender__career__institution_id__in=institution_ids),
            status=TransferRiskAlert.Status.OPEN,
        )
    else:
        alerts = TransferRiskAlert.objects.filter(status=TransferRiskAlert.Status.OPEN)
    alerts = alerts.select_related("request__sender__career")
    alert_rows = [{"id": str(alert.pk), "requestId": str(alert.request_id), "code": alert.code,
                   "description": alert.description, "career": alert.request.sender.career.name,
                   "resolvedReason": alert.resolution_reason} for alert in alerts]
    return Response({
        "enrollments": [_enrollment_payload(row) for row in enrollments],
        "recipients": [_enrollment_payload(row) for row in recipients],
        "sources": sources, "requests": request_payloads, "reviewQueue": review_queue,
        "riskAlerts": alert_rows,
        "monthly": _monthly_status(request.user),
        "canReviewTransfers": request.user.is_superuser or current_role_assignments(request.user).filter(
            role__in=(RoleAssignment.Role.CAREER_ADMIN, RoleAssignment.Role.COORDINATOR,
                      RoleAssignment.Role.INSTITUTION_ADMIN, RoleAssignment.Role.TEACHER,
                      RoleAssignment.Role.EVIDENCE_REVIEWER, RoleAssignment.Role.AUXILIARY),
        ).exists(),
        "balances": [{
            "enrollment": str(enrollment.pk), "career": enrollment.career.name, "careerCode": enrollment.career.code,
            "period": enrollment.period.name,
            "merit": PointsMovement.objects.filter(enrollment=enrollment).aggregate(total=Sum("points"))["total"] or 0,
            "sent": -(TransferMovement.objects.filter(enrollment=enrollment, side=TransferMovement.Side.DEBIT).aggregate(total=Sum("points"))["total"] or 0),
            "received": TransferMovement.objects.filter(enrollment=enrollment, side=TransferMovement.Side.CREDIT).aggregate(total=Sum("points"))["total"] or 0,
            "adjustments": TransferAdjustment.objects.filter(enrollment=enrollment).aggregate(total=Sum("points"))["total"] or 0,
            "transferable": sum(entry["available"] for entry in transferable_sources(enrollment)),
        } for enrollment in own.select_related("career", "period")],
        "limits": {"perRequest": MAX_PER_REQUEST, "perMonth": MAX_PER_MONTH, "monthBasis": "America/La_Paz"},
    })


def _monthly_status(user):
    start, end = _month_window(timezone.localdate())
    profile_ids = Enrollment.objects.filter(student__user=user).values_list("student_id", flat=True).distinct()
    sent = sum(_monthly_reserved(Enrollment.objects.filter(student_id=student_id).select_related("student").first(), start, end) for student_id in profile_ids)
    return {"sentOrPending": sent, "remaining": max(0, MAX_PER_MONTH - sent), "limit": MAX_PER_MONTH}


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def api_cancel_transfer(request, request_id):
    try:
        transfer = cancel_transfer_request(actor=request.user, request_id=request_id)
    except TransferRequest.DoesNotExist:
        return Response({"detail": "Solicitud no encontrada."}, status=404)
    except PermissionDenied as exc:
        return Response({"detail": str(exc)}, status=403)
    except ValidationError as exc:
        return Response({"detail": " ".join(exc.messages)}, status=400)
    return Response({"status": transfer.status})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def api_review_transfer(request, request_id):
    serializer = ReviewSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    try:
        transfer = review_transfer(actor=request.user, request_id=request_id,
                                   decision=serializer.validated_data["decision"],
                                   reason=serializer.validated_data["reason"])
    except TransferRequest.DoesNotExist:
        return Response({"detail": "Solicitud no encontrada."}, status=404)
    except PermissionDenied as exc:
        return Response({"detail": str(exc)}, status=403)
    except ValidationError as exc:
        return Response({"detail": " ".join(exc.messages)}, status=400)
    transfer = TransferRequest.objects.select_related(
        "sender__student__user", "sender__career", "sender__period",
        "recipient__student__user", "recipient__career", "recipient__period", "activity__category",
    ).prefetch_related("reviews__reviewer", "risk_alerts").get(pk=transfer.pk)
    return Response(_request_payload(transfer, request.user))


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def api_resolve_risk(request, alert_id):
    try:
        alert = resolve_risk_alert(actor=request.user, alert_id=alert_id, reason=request.data.get("reason", ""))
    except TransferRiskAlert.DoesNotExist:
        return Response({"detail": "Alerta no encontrada."}, status=404)
    except PermissionDenied as exc:
        return Response({"detail": str(exc)}, status=403)
    except ValidationError as exc:
        return Response({"detail": " ".join(exc.messages)}, status=400)
    return Response({"status": alert.status})
