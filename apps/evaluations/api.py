from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import F, Q
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.accounts.models import RoleAssignment
from apps.accounts.permissions import current_role_assignments
from apps.academics.models import CourseOffering, Enrollment
from apps.activities.services import can_manage_spd
from .models import EvaluationAggregate, EvaluationCampaign, EvaluationEligibility, EvaluationTarget
from .services import (
    MINIMUM_PRIVACY_THRESHOLD, QUESTIONS, SCALE_LABELS, cancel_campaign, close_campaign,
    _valid_assignments, create_campaign, manageable_careers, publish_campaign,
    publish_results, submit_ballot,
)


class CampaignSerializer(serializers.Serializer):
    offeringId = serializers.UUIDField()
    title = serializers.CharField(max_length=180)
    opensAt = serializers.DateTimeField()
    closesAt = serializers.DateTimeField()
    minimumResponses = serializers.IntegerField(min_value=MINIMUM_PRIVACY_THRESHOLD, max_value=100, default=5)


class BallotSerializer(serializers.Serializer):
    targetId = serializers.UUIDField()
    answers = serializers.DictField()


def _manager(user, career):
    return user.is_superuser or can_manage_spd(user, career)


def _campaign_card(campaign, *, manager=False):
    targets = []
    for target in campaign.targets.select_related("subject", "assignment"):
        aggregate = EvaluationAggregate.objects.filter(campaign=campaign, target=target).first()
        result = None
        if aggregate:
            result = {"state": aggregate.state}
            if aggregate.state == EvaluationAggregate.State.PUBLISHED:
                result.update({"responseCount": aggregate.response_count, "metrics": aggregate.metrics})
        targets.append({
            "id": str(target.pk), "subject": target.subject_name, "role": target.get_subject_role_display(),
            "result": result,
        })
    return {
        "id": str(campaign.pk), "title": campaign.title, "version": campaign.version,
        "status": campaign.status, "statusLabel": campaign.get_status_display(),
        "career": campaign.career.name, "careerCode": campaign.career.code,
        "period": campaign.period.name, "course": campaign.offering.course.name,
        "courseCode": campaign.offering.course.code, "group": campaign.offering.group_code,
        "opensAt": campaign.opens_at.isoformat(), "closesAt": campaign.closes_at.isoformat(),
        "minimumResponses": campaign.minimum_responses,
        "canPublish": manager and campaign.status == EvaluationCampaign.Status.DRAFT,
        "canClose": manager and campaign.status == EvaluationCampaign.Status.OPEN,
        "canCancel": manager and campaign.status == EvaluationCampaign.Status.DRAFT,
        "canPublishResults": manager and campaign.status == EvaluationCampaign.Status.CLOSED,
        "targets": targets,
    }


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def api_evaluations(request):
    if request.method == "POST":
        serializer = CampaignSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        try:
            campaign = create_campaign(
                actor=request.user, offering_id=values["offeringId"], title=values["title"],
                opens_at=values["opensAt"], closes_at=values["closesAt"],
                minimum_responses=values["minimumResponses"],
            )
        except CourseOffering.DoesNotExist:
            return Response({"detail": "No se encontró el grupo solicitado."}, status=404)
        except PermissionDenied as exc:
            return Response({"detail": str(exc)}, status=403)
        except (ValidationError, ValueError, TypeError) as exc:
            return Response({"detail": " ".join(exc.messages) if isinstance(exc, ValidationError) else str(exc)}, status=400)
        return Response(_campaign_card(campaign, manager=True), status=status.HTTP_201_CREATED)

    user = request.user
    careers = manageable_careers(user)
    offerings = CourseOffering.objects.filter(
        course__career_id__in=careers,
        teaching_assignments__active=True,
    ).distinct().select_related("course__career", "period").order_by("course__career__code", "period__starts_on", "course__code", "group_code")
    offering_rows = [{
        "id": str(row.pk), "career": row.course.career.name, "careerCode": row.course.career.code,
        "period": row.period.name, "periodCode": row.period.code,
        "course": row.course.name, "courseCode": row.course.code, "group": row.group_code,
    } for row in offerings if _manager(user, row.course.career) and _valid_assignments(row)]

    campaigns = EvaluationCampaign.objects.select_related("career", "period", "offering__course").prefetch_related("targets__subject", "targets__assignment")
    if not user.is_superuser:
        campaigns = campaigns.filter(career_id__in=careers)
    managed = [_campaign_card(row, manager=True) for row in campaigns]

    student_eligibilities = EvaluationEligibility.objects.filter(
        enrollment__student__user=user,
        campaign__status__in=(EvaluationCampaign.Status.OPEN, EvaluationCampaign.Status.CLOSED, EvaluationCampaign.Status.PUBLISHED),
        enrollment__status=Enrollment.Status.ACTIVE,
        enrollment__course_enrollments__offering_id=F("campaign__offering_id"),
        enrollment__course_enrollments__active=True,
    ).distinct().select_related("campaign__career", "campaign__period", "campaign__offering__course", "target__subject")
    my_surveys = []
    for eligibility in student_eligibilities:
        campaign = eligibility.campaign
        now = timezone.now()
        if campaign.status == EvaluationCampaign.Status.OPEN and not (campaign.opens_at <= now < campaign.closes_at):
            continue
        my_surveys.append({
            "campaignId": str(campaign.pk), "targetId": str(eligibility.target_id),
            "title": campaign.title, "version": campaign.version,
            "status": campaign.status, "course": campaign.offering.course.name,
            "courseCode": campaign.offering.course.code, "group": campaign.offering.group_code,
            "period": campaign.period.name, "subject": eligibility.target.subject_name,
            "role": eligibility.target.get_subject_role_display(), "opensAt": campaign.opens_at.isoformat(),
            "closesAt": campaign.closes_at.isoformat(), "answered": eligibility.answered,
            "canRespond": campaign.status == EvaluationCampaign.Status.OPEN and not eligibility.answered,
        })

    active_today = timezone.localdate()
    own_targets = EvaluationTarget.objects.filter(
        subject=user, campaign__status=EvaluationCampaign.Status.PUBLISHED,
        assignment__active=True, assignment__starts_on__lte=active_today,
    ).filter(Q(assignment__ends_on__isnull=True) | Q(assignment__ends_on__gte=active_today)).select_related(
        "campaign__career", "campaign__period", "campaign__offering__course",
    ).prefetch_related("aggregates")
    subject_results = []
    for target in own_targets:
        if target.assignment.user_id != user.pk or not current_role_assignments(user).filter(
            role=target.subject_role, scope=RoleAssignment.Scope.GROUP,
            group=target.campaign.offering,
        ).exists():
            continue
        aggregate = EvaluationAggregate.objects.filter(target=target, state=EvaluationAggregate.State.PUBLISHED).first()
        if aggregate:
            subject_results.append({
                "campaign": target.campaign.title, "version": target.campaign.version,
                "career": target.campaign.career.name, "period": target.campaign.period.name,
                "course": target.campaign.offering.course.name, "courseCode": target.campaign.offering.course.code,
                "group": target.campaign.offering.group_code, "responseCount": aggregate.response_count,
                "metrics": aggregate.metrics, "publishedAt": aggregate.published_at.isoformat(),
            })
    return Response({
        "questionnaire": [{"code": code, "label": label} for code, label in QUESTIONS],
        "scale": [{"value": key, "label": value} for key, value in SCALE_LABELS.items()],
        "minimumPrivacyThreshold": MINIMUM_PRIVACY_THRESHOLD,
        "mySurveys": my_surveys, "subjectResults": subject_results,
        "campaigns": managed, "offerings": offering_rows,
        "canManage": bool(careers) or user.is_superuser,
    })


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def api_respond(request):
    serializer = BallotSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    try:
        submit_ballot(actor=request.user, target_id=serializer.validated_data["targetId"], response=serializer.validated_data["answers"])
    except PermissionDenied as exc:
        return Response({"detail": str(exc)}, status=403)
    except EvaluationEligibility.DoesNotExist:
        return Response({"detail": "No tienes habilitación para responder esta evaluación."}, status=403)
    except EvaluationCampaign.DoesNotExist:
        return Response({"detail": "La campaña ya no está disponible."}, status=404)
    except ValidationError as exc:
        return Response({"detail": " ".join(exc.messages)}, status=400)
    return Response({"detail": "Respuesta registrada de forma anónima."}, status=status.HTTP_201_CREATED)


def _campaign_action(request, campaign_id, action):
    reason = request.data.get("reason", "")
    try:
        if action == "open":
            campaign = publish_campaign(actor=request.user, campaign_id=campaign_id)
        elif action == "close":
            campaign = close_campaign(actor=request.user, campaign_id=campaign_id, reason=reason or "Cierre por coordinación.")
        elif action == "publish-results":
            campaign, _aggregates = publish_results(actor=request.user, campaign_id=campaign_id)
        else:
            campaign = cancel_campaign(actor=request.user, campaign_id=campaign_id, reason=reason)
    except EvaluationCampaign.DoesNotExist:
        return Response({"detail": "No se encontró la campaña."}, status=404)
    except PermissionDenied as exc:
        return Response({"detail": str(exc)}, status=403)
    except ValidationError as exc:
        return Response({"detail": " ".join(exc.messages)}, status=400)
    return Response(_campaign_card(campaign, manager=True))


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def api_open_campaign(request, campaign_id):
    return _campaign_action(request, campaign_id, "open")


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def api_close_campaign(request, campaign_id):
    return _campaign_action(request, campaign_id, "close")


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def api_publish_results(request, campaign_id):
    return _campaign_action(request, campaign_id, "publish-results")


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def api_cancel_campaign(request, campaign_id):
    return _campaign_action(request, campaign_id, "cancel")
