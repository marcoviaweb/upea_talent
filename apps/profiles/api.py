"""Same-origin session API used by the React trajectory portal."""
from decimal import Decimal

from django.contrib.auth import authenticate, login, logout
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404
from django.middleware.csrf import get_token
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from rest_framework import serializers, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from apps.accounts.models import RoleAssignment
from apps.accounts.permissions import current_role_assignments, visible_course_enrollments
from apps.academics.models import CourseEnrollment, CourseOffering, GradeRecord

from .forms import StudentProjectForm, StudentSkillForm
from .models import DevelopmentRecord, StudentProject, StudentSkill
from .services import (
    enrollment_for_actor,
    review_development_record,
    save_development_record,
    student_enrollments,
)
from .views import assigned_teacher_offerings

RECORD_TYPES = {"project": (StudentProject, StudentProjectForm), "skill": (StudentSkill, StudentSkillForm)}


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    password = serializers.CharField(trim_whitespace=False, write_only=True)


class DevelopmentInputSerializer(serializers.Serializer):
    intent = serializers.ChoiceField(choices=("draft", "submit"), default="submit")


class ReviewInputSerializer(serializers.Serializer):
    outcome = serializers.ChoiceField(choices=("approve", "observe"))
    note = serializers.CharField(required=False, allow_blank=True, max_length=500)

    def validate(self, attrs):
        attrs.setdefault("note", "")
        if attrs["outcome"] == "observe" and not attrs.get("note", "").strip():
            raise serializers.ValidationError({"note": "Explica qué información debe corregirse."})
        return attrs


def _person_name(user):
    return user.get_full_name().strip() or user.get_username()


def _user_payload(user):
    return {"id": str(user.pk), "username": user.get_username(), "name": _person_name(user)}


def _enrollment_payload(enrollment):
    return {
        "id": str(enrollment.pk),
        "career": {"code": enrollment.career.code, "name": enrollment.career.name},
        "period": {"code": enrollment.period.code, "name": enrollment.period.name,
                   "startsOn": enrollment.period.starts_on.isoformat(), "endsOn": enrollment.period.ends_on.isoformat()},
        "semester": enrollment.semester_number,
        "status": enrollment.status,
        "statusLabel": enrollment.get_status_display(),
    }


def _record_payload(record, kind, owner):
    payload = {
        "id": str(record.pk), "type": kind, "status": record.status,
        "statusLabel": record.get_status_display(), "createdAt": record.created_at.isoformat(),
        "updatedAt": record.updated_at.isoformat(), "reviewNote": record.review_note,
        "validatedBy": _person_name(record.validated_by) if record.validated_by_id else None,
        "validatedAt": record.validated_at.isoformat() if record.validated_at else None,
        "canEdit": owner and record.status in {DevelopmentRecord.Status.DECLARED, DevelopmentRecord.Status.NEEDS_CHANGES},
    }
    if kind == "project":
        payload.update({"title": record.title, "description": record.description, "role": record.role,
                        "startedOn": record.started_on.isoformat() if record.started_on else None,
                        "completedOn": record.completed_on.isoformat() if record.completed_on else None})
    else:
        payload.update({"name": record.name, "proficiencyLabel": record.proficiency_label,
                        "description": record.description})
    return payload


@api_view(["GET"])
@permission_classes([AllowAny])
@ensure_csrf_cookie
def csrf_token(request):
    return Response({"csrfToken": get_token(request)})


@api_view(["POST"])
@permission_classes([AllowAny])
def api_login(request):
    serializer = LoginSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    user = authenticate(request, username=serializer.validated_data["username"], password=serializer.validated_data["password"])
    if user is None or not user.is_active:
        return Response({"detail": "Usuario o contraseña incorrectos."}, status=status.HTTP_400_BAD_REQUEST)
    login(request, user)
    return Response({"user": _user_payload(user), "csrfToken": get_token(request)})


# DRF exempts function-based API views from Django's middleware; preserve an
# explicit CSRF check for the anonymous session-creation endpoint.
api_login = csrf_protect(api_login)
api_login.csrf_exempt = False


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def api_logout(request):
    logout(request)
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def api_home(request):
    enrollments = list(student_enrollments(request.user))
    offerings = assigned_teacher_offerings(request.user)
    can_manage_career = current_role_assignments(request.user).filter(
        role__in=(RoleAssignment.Role.COORDINATOR, RoleAssignment.Role.CAREER_ADMIN, RoleAssignment.Role.INSTITUTION_ADMIN)
    ).exists() or request.user.is_superuser
    if not enrollments and not offerings.exists() and not can_manage_career:
        raise PermissionDenied("Tu cuenta no tiene una matrícula estudiantil ni grupos docentes vigentes.")
    groups = [{
        "id": str(offering.pk), "course": {"code": offering.course.code, "name": offering.course.name,
                                             "career": offering.course.career.name},
        "period": offering.period.name, "group": offering.group_code,
        "studentCount": offering.student_count,
    } for offering in offerings]
    return Response({"user": _user_payload(request.user),
                     "enrollments": [_enrollment_payload(enrollment) for enrollment in enrollments],
                     "groups": groups,
                     "canRegisterVerifiedActivity": can_manage_career})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def api_group_roster(request, offering_id):
    offering = assigned_teacher_offerings(request.user).filter(pk=offering_id).first()
    if not offering:
        raise Http404("Grupo no encontrado.")
    roster = visible_course_enrollments(request.user).filter(offering=offering).select_related(
        "enrollment__student__user", "enrollment__career", "enrollment__period"
    ).order_by("enrollment__student__user__last_name", "enrollment__student__user__first_name")
    return Response({
        "offering": {"id": str(offering.pk), "course": offering.course.name, "code": offering.course.code,
                     "period": offering.period.name, "group": offering.group_code},
        "students": [{"enrollmentId": str(row.enrollment_id), "name": _person_name(row.enrollment.student.user),
                      "studentNumber": row.enrollment.student.student_number,
                      "enrollmentStatus": row.enrollment.get_status_display()} for row in roster],
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def api_enrollment_profile(request, enrollment_id):
    enrollment = enrollment_for_actor(request.user, enrollment_id)
    owner = (enrollment.student.user_id == request.user.pk
             and student_enrollments(request.user).filter(pk=enrollment.pk).exists())
    project_rows = list(StudentProject.objects.filter(enrollment=enrollment).select_related("validated_by"))
    skill_rows = list(StudentSkill.objects.filter(enrollment=enrollment).select_related("validated_by"))
    grade_rows = list(GradeRecord.objects.filter(enrollment=enrollment, status=GradeRecord.Status.VERIFIED).select_related(
        "offering__course", "offering__period", "verified_by", "supersedes"
    ))
    grades = [{
        "id": str(grade.pk), "course": grade.offering.course.name, "courseCode": grade.offering.course.code,
        "group": grade.offering.group_code, "period": grade.offering.period.name,
        "value": str(grade.grade_value), "scale": str(grade.scale_snapshot),
        "threshold": str(grade.pass_threshold_snapshot), "passed": grade.grade_value >= grade.pass_threshold_snapshot,
        "source": grade.source or "No indicada", "verifiedBy": _person_name(grade.verified_by),
        "verifiedAt": grade.verified_at.isoformat() if grade.verified_at else None,
        "correctsValue": str(grade.supersedes.grade_value) if grade.supersedes_id else None,
    } for grade in grade_rows]
    average = (sum((Decimal(row["value"]) for row in grades), Decimal("0")) / len(grades)).quantize(Decimal("0.01")) if grades else None
    courses = CourseEnrollment.objects.filter(enrollment=enrollment, active=True).select_related(
        "offering__course", "offering__period"
    )
    return Response({
        "enrollment": _enrollment_payload(enrollment),
        "student": {"name": _person_name(enrollment.student.user), "studentNumber": enrollment.student.student_number},
        "isOwner": owner, "canDeclare": owner and enrollment.status == enrollment.Status.ACTIVE,
        "grades": grades, "average": str(average) if average is not None else None,
        "courses": [{"code": row.offering.course.code, "name": row.offering.course.name,
                     "group": row.offering.group_code} for row in courses],
        "projects": [_record_payload(row, "project", owner) for row in project_rows],
        "skills": [_record_payload(row, "skill", owner) for row in skill_rows],
        "counts": {"validatedProjects": sum(row.status == DevelopmentRecord.Status.VALIDATED for row in project_rows),
                   "validatedSkills": sum(row.status == DevelopmentRecord.Status.VALIDATED for row in skill_rows)},
    })


def _record_form(kind, data, instance=None):
    model_and_form = RECORD_TYPES.get(kind)
    if not model_and_form:
        raise Http404("Tipo de declaración no encontrado.")
    return model_and_form[1](data=data, instance=instance)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def api_create_development(request, enrollment_id, record_type):
    enrollment = enrollment_for_actor(request.user, enrollment_id)
    if enrollment.student.user_id != request.user.pk or not student_enrollments(request.user).filter(pk=enrollment.pk).exists():
        raise Http404("Trayectoria no encontrada.")
    form = _record_form(record_type, request.data)
    input_serializer = DevelopmentInputSerializer(data=request.data)
    input_serializer.is_valid(raise_exception=True)
    if not form.is_valid():
        return Response({"errors": form.errors.get_json_data()}, status=status.HTTP_400_BAD_REQUEST)
    record = form.save(commit=False)
    try:
        saved = save_development_record(actor=request.user, enrollment=enrollment, record=record,
                                        submit=input_serializer.validated_data["intent"] == "submit")
    except ValidationError as exc:
        return Response({"detail": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
    return Response({"record": _record_payload(saved, record_type, True)}, status=status.HTTP_201_CREATED)


@api_view(["PATCH"])
@permission_classes([IsAuthenticated])
def api_update_development(request, enrollment_id, record_type, record_id):
    enrollment = enrollment_for_actor(request.user, enrollment_id)
    if enrollment.student.user_id != request.user.pk or not student_enrollments(request.user).filter(pk=enrollment.pk).exists():
        raise Http404("Trayectoria no encontrada.")
    model_and_form = RECORD_TYPES.get(record_type)
    if not model_and_form:
        raise Http404("Tipo de declaración no encontrado.")
    record = model_and_form[0].objects.filter(pk=record_id, enrollment=enrollment).first()
    if not record:
        raise Http404("Declaración no encontrada.")
    form = _record_form(record_type, request.data, instance=record)
    input_serializer = DevelopmentInputSerializer(data=request.data)
    input_serializer.is_valid(raise_exception=True)
    if not form.is_valid():
        return Response({"errors": form.errors.get_json_data()}, status=status.HTTP_400_BAD_REQUEST)
    updated = form.save(commit=False)
    try:
        saved = save_development_record(actor=request.user, enrollment=enrollment, record=updated,
                                        submit=input_serializer.validated_data["intent"] == "submit")
    except ValidationError as exc:
        return Response({"detail": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
    return Response({"record": _record_payload(saved, record_type, True)})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def api_review_development(request, record_type, record_id):
    model_and_form = RECORD_TYPES.get(record_type)
    if not model_and_form:
        raise Http404("Tipo de declaración no encontrado.")
    record = model_and_form[0].objects.select_related("enrollment__student__user").filter(pk=record_id).first()
    if not record:
        raise Http404("Declaración no encontrada.")
    enrollment_for_actor(request.user, record.enrollment_id)
    serializer = ReviewInputSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    try:
        reviewed = review_development_record(actor=request.user, record=record, **serializer.validated_data)
    except PermissionDenied as exc:
        raise Http404("Declaración no encontrada.") from exc
    except ValidationError as exc:
        return Response({"detail": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
    return Response({"record": _record_payload(reviewed, record_type, False)})
