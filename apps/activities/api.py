from pathlib import Path

from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.accounts.models import RoleAssignment
from apps.accounts.permissions import current_role_assignments, visible_course_enrollments
from apps.academics.models import CourseEnrollment, Enrollment
from .models import Activity, ActivityCategory, EvidenceFile, PointsMovement, Regulation, ReviewDecision
from .services import can_manage_spd, can_review, can_revoke, current_regulation, record_verified_activity, resubmit_activity, review_activity, revoke_activity, submit_activity


def validate_evidence_file(file):
    ext = Path(file.name).suffix.lower()
    if ext not in {".pdf", ".jpg", ".jpeg", ".png"}:
        raise serializers.ValidationError("Solo se admiten archivos PDF, JPG o PNG.")
    if file.size > 10 * 1024 * 1024:
        raise serializers.ValidationError("El tamaño máximo por archivo es 10 MB.")
    signature = file.read(8)
    file.seek(0)
    valid = {".pdf": signature.startswith(b"%PDF-"), ".png": signature.startswith(b"\x89PNG\r\n\x1a\n"), ".jpg": signature.startswith(b"\xff\xd8\xff"), ".jpeg": signature.startswith(b"\xff\xd8\xff")}
    if not valid[ext]:
        raise serializers.ValidationError("El contenido del archivo no coincide con su extensión.")
    return file


class EvidenceUploadSerializer(serializers.Serializer):
    file = serializers.FileField(validators=[validate_evidence_file])


class SubmissionSerializer(EvidenceUploadSerializer):
    category = serializers.UUIDField()
    title = serializers.CharField(max_length=160)
    description = serializers.CharField(max_length=3000)
    occurredOn = serializers.DateField()
    source = serializers.CharField(max_length=200, required=False, allow_blank=True)
    courseEnrollment = serializers.UUIDField(required=False, allow_null=True)

    def validate_occurredOn(self, value):
        if value > timezone.localdate():
            raise serializers.ValidationError("La fecha de realización no puede ser futura.")
        return value


class ReviewSerializer(serializers.Serializer):
    outcome = serializers.ChoiceField(choices=("approve", "observe", "reject"))
    note = serializers.CharField(max_length=500, required=False, allow_blank=True)

    def validate(self, attrs):
        attrs.setdefault("note", "")
        if attrs["outcome"] in {"observe", "reject"} and not attrs["note"].strip():
            raise serializers.ValidationError({"note": "Explica el motivo o la información faltante."})
        return attrs


class VerifiedActivitySerializer(serializers.Serializer):
    enrollment = serializers.UUIDField()
    category = serializers.UUIDField()
    title = serializers.CharField(max_length=160)
    description = serializers.CharField(max_length=3000)
    occurredOn = serializers.DateField()
    source = serializers.CharField(max_length=200)

    def validate_occurredOn(self, value):
        if value > timezone.localdate():
            raise serializers.ValidationError("La fecha de realización no puede ser futura.")
        return value


def _file_payload(file):
    return {"id": str(file.pk), "name": file.original_name, "size": file.size, "contentType": file.content_type, "version": file.version, "url": f"/api/v1/evidence/files/{file.pk}/"}


def _activity_payload(activity, actor):
    owner = activity.enrollment.student.user_id == actor.pk
    return {
        "id": str(activity.pk), "title": activity.title, "description": activity.description, "occurredOn": activity.occurred_on.isoformat(),
        "source": activity.source, "status": activity.status, "statusLabel": activity.get_status_display(),
        "category": {"id": str(activity.category_id), "code": activity.category.code, "name": activity.category.name, "criterion": activity.category.criterion, "points": activity.category.points, "transferable": activity.category.transferable},
        "student": activity.enrollment.student.user.get_full_name() or activity.enrollment.student.user.username,
        "career": activity.enrollment.career.name, "period": activity.enrollment.period.name,
        "createdAt": activity.created_at.isoformat(), "reviewedAt": activity.reviewed_at.isoformat() if activity.reviewed_at else None,
        "reviewedBy": (activity.reviewed_by.get_full_name() or activity.reviewed_by.username) if activity.reviewed_by_id else None,
        "isOwner": owner, "canReview": not owner and can_review(actor, activity),
        "canRevoke": activity.status == Activity.Status.APPROVED and can_revoke(actor, activity),
        "files": [_file_payload(item) for item in activity.files.all()],
        "reviews": [{"outcome": row.outcome, "note": row.note, "reviewer": row.reviewer.get_full_name() or row.reviewer.username, "createdAt": row.created_at.isoformat()} for row in activity.reviews.select_related("reviewer")],
    }


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser])
def api_evidence(request):
    if request.method == "GET":
        owned = Activity.objects.filter(enrollment__student__user=request.user)
        reviewable = Activity.objects.filter(enrollment__in=visible_course_enrollments(request.user).values("enrollment_id"))
        roles = current_role_assignments(request.user)
        career_ids = roles.filter(role__in=(RoleAssignment.Role.CAREER_ADMIN, RoleAssignment.Role.COORDINATOR), scope=RoleAssignment.Scope.CAREER).values("career_id")
        institution_ids = roles.filter(role=RoleAssignment.Role.INSTITUTION_ADMIN, scope=RoleAssignment.Scope.INSTITUTION).values("institution_id")
        administrative = Activity.objects.filter(enrollment__career_id__in=career_ids) | Activity.objects.filter(enrollment__career__institution_id__in=institution_ids)
        if request.user.is_superuser:
            administrative = Activity.objects.all()
        rows = (owned | reviewable | administrative).distinct().select_related("enrollment__student__user", "enrollment__career", "enrollment__period", "category__regulation", "reviewed_by").prefetch_related("files", "reviews__reviewer")
        return Response({"activities": [_activity_payload(row, request.user) for row in rows]})
    serializer = SubmissionSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    values = serializer.validated_data
    enrollment = get_object_or_404(Enrollment.objects.select_related("career", "student__user"), pk=request.data.get("enrollment"), student__user=request.user)
    category = get_object_or_404(ActivityCategory.objects.select_related("regulation"), pk=values["category"])
    course_enrollment = None
    if values.get("courseEnrollment"):
        course_enrollment = get_object_or_404(CourseEnrollment, pk=values["courseEnrollment"])
    try:
        activity = submit_activity(user=request.user, enrollment=enrollment, category=category, title=values["title"], description=values["description"], occurred_on=values["occurredOn"], source=values.get("source", ""), uploaded_file=values["file"], course_enrollment=course_enrollment)
    except (PermissionDenied, ValidationError) as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN if isinstance(exc, PermissionDenied) else status.HTTP_400_BAD_REQUEST)
    activity = Activity.objects.select_related("enrollment__student__user", "enrollment__career", "enrollment__period", "category__regulation").prefetch_related("files", "reviews").get(pk=activity.pk)
    return Response({"activity": _activity_payload(activity, request.user)}, status=status.HTTP_201_CREATED)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def api_evidence_candidates(request):
    roles = current_role_assignments(request.user)
    career_ids = roles.filter(role__in=(RoleAssignment.Role.CAREER_ADMIN, RoleAssignment.Role.COORDINATOR), scope=RoleAssignment.Scope.CAREER).values("career_id")
    institution_ids = roles.filter(role=RoleAssignment.Role.INSTITUTION_ADMIN, scope=RoleAssignment.Scope.INSTITUTION).values("institution_id")
    rows = Enrollment.objects.filter(status="active").filter(Q(career_id__in=career_ids) | Q(career__institution_id__in=institution_ids)).select_related("student__user", "career", "period").order_by("career__code", "student__student_number")
    if request.user.is_superuser:
        rows = Enrollment.objects.filter(status="active").select_related("student__user", "career", "period").order_by("career__code", "student__student_number")
    if not rows.exists():
        if not request.user.is_superuser and not roles.filter(role__in=(RoleAssignment.Role.CAREER_ADMIN, RoleAssignment.Role.COORDINATOR, RoleAssignment.Role.INSTITUTION_ADMIN)).exists():
            return Response({"detail": "No tienes ámbitos administrativos para registrar méritos."}, status=403)
    return Response({"enrollments": [{"id": str(row.pk), "student": row.student.user.get_full_name() or row.student.user.username, "studentNumber": row.student.student_number, "career": row.career.name, "careerCode": row.career.code, "period": row.period.name} for row in rows]})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def api_record_verified(request):
    serializer = VerifiedActivitySerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    values = serializer.validated_data
    enrollment = get_object_or_404(Enrollment.objects.select_related("career__institution", "student__user", "period"), pk=values["enrollment"])
    category = get_object_or_404(ActivityCategory.objects.select_related("regulation__career"), pk=values["category"])
    if not can_manage_spd(request.user, enrollment.career):
        return Response({"detail": "No tienes autorización para esta carrera."}, status=404)
    try:
        activity = record_verified_activity(actor=request.user, enrollment=enrollment, category=category, title=values["title"], description=values["description"], occurred_on=values["occurredOn"], source=values["source"])
    except PermissionDenied as exc:
        return Response({"detail": str(exc)}, status=403)
    except ValidationError as exc:
        return Response({"detail": str(exc)}, status=400)
    activity = Activity.objects.select_related("enrollment__student__user", "enrollment__career", "enrollment__period", "category__regulation").prefetch_related("files", "reviews").get(pk=activity.pk)
    return Response({"activity": _activity_payload(activity, request.user)}, status=201)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def api_spd(request):
    own_enrollments = Enrollment.objects.filter(student__user=request.user).select_related("career")
    group_view = not own_enrollments.exists()
    visible_roster = visible_course_enrollments(request.user).select_related(
        "enrollment__student__user", "enrollment__career", "enrollment__period",
        "offering__course",
    )
    if group_view:
        ledger_enrollments = Enrollment.objects.filter(
            pk__in=visible_roster.values("enrollment_id"), status="active"
        ).select_related("student__user", "career", "period").distinct()
    else:
        ledger_enrollments = own_enrollments.select_related("student__user", "period")
    careers = {str(enrollment.career_id): enrollment.career for enrollment in own_enrollments}
    if group_view:
        careers.update({str(enrollment.career_id): enrollment.career for enrollment in ledger_enrollments})
    published = Regulation.objects.filter(published=True, effective_from__lte=timezone.localdate()).filter(
        Q(effective_to__isnull=True) | Q(effective_to__gte=timezone.localdate())
    ).select_related("career")
    public_careers = {str(reg.career_id): reg.career for reg in published}
    selected = request.query_params.get("career")
    if selected:
        public_careers = {key: item for key, item in public_careers.items() if key == selected or item.code == selected}
    regulations = []
    totals = []
    for career in public_careers.values():
        regulation = current_regulation(career)
        if regulation:
            regulations.append({"id": str(regulation.pk), "career": career.name, "careerCode": career.code, "version": regulation.version, "title": regulation.title, "effectiveFrom": regulation.effective_from.isoformat(), "effectiveTo": regulation.effective_to.isoformat() if regulation.effective_to else None, "categories": [{"id": str(row.pk), "code": row.code, "name": row.name, "criterion": row.criterion, "points": row.points, "transferable": row.transferable} for row in regulation.categories.filter(active=True)]})
    for career in careers.values():
        for enrollment in ledger_enrollments.filter(career=career):
            movements = PointsMovement.objects.filter(enrollment=enrollment)
            total = sum(movements.values_list("points", flat=True))
            level = "Explorador" if total < 100 else "Participante" if total < 250 else "Desarrollador" if total < 500 else "Líder" if total < 750 else "Talento destacado"
            row = {"enrollment": str(enrollment.pk), "career": career.name, "careerCode": career.code, "period": enrollment.period.name, "points": total, "level": level, "movements": [{"id": str(movement.pk), "points": movement.points, "reason": movement.reason, "category": movement.category.name, "regulationVersion": movement.regulation.version, "date": movement.created_at.isoformat(), "activity": str(movement.activity_id) if movement.activity_id else None} for movement in movements.select_related("category", "regulation")]}
            if group_view:
                row.update({"student": enrollment.student.user.get_full_name() or enrollment.student.user.username, "studentNumber": enrollment.student.student_number})
            totals.append(row)
    return Response({"regulations": regulations, "totals": totals, "groupView": group_view, "levelThresholds": [{"name": "Explorador", "from": 0, "to": 99}, {"name": "Participante", "from": 100, "to": 249}, {"name": "Desarrollador", "from": 250, "to": 499}, {"name": "Líder", "from": 500, "to": 749}, {"name": "Talento destacado", "from": 750, "to": None}]})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def api_review(request, activity_id):
    activity = get_object_or_404(Activity.objects.select_related("enrollment", "category__regulation"), pk=activity_id)
    serializer = ReviewSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    try:
        activity = review_activity(actor=request.user, activity=activity, outcome=serializer.validated_data["outcome"], note=serializer.validated_data["note"])
    except PermissionDenied as exc:
        return Response({"detail": str(exc)}, status=403)
    except ValidationError as exc:
        return Response({"detail": str(exc)}, status=400)
    return Response({"activity": _activity_payload(activity, request.user)})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def api_revoke(request, activity_id):
    activity = get_object_or_404(Activity, pk=activity_id)
    try:
        activity = revoke_activity(actor=request.user, activity=activity, reason=str(request.data.get("reason", ""))[:300])
    except PermissionDenied as exc:
        return Response({"detail": str(exc)}, status=403)
    except ValidationError as exc:
        return Response({"detail": str(exc)}, status=400)
    return Response({"status": activity.status})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser])
def api_resubmit(request, activity_id):
    upload = EvidenceUploadSerializer(data=request.data)
    upload.is_valid(raise_exception=True)
    file_validation = upload.validated_data["file"]
    activity = get_object_or_404(Activity.objects.select_related("enrollment"), pk=activity_id)
    try:
        activity = resubmit_activity(actor=request.user, activity=activity, uploaded_file=file_validation)
    except PermissionDenied as exc:
        return Response({"detail": str(exc)}, status=403)
    except ValidationError as exc:
        return Response({"detail": str(exc)}, status=400)
    return Response({"status": activity.status})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def api_evidence_file(request, file_id):
    evidence = get_object_or_404(EvidenceFile.objects.select_related("activity__enrollment"), pk=file_id)
    is_owner = evidence.activity.enrollment.student.user_id == request.user.pk
    if not is_owner and not can_review(request.user, evidence.activity):
        raise Http404("Archivo no encontrado.")
    response = FileResponse(evidence.file.open("rb"), as_attachment=True, filename=evidence.original_name)
    response["Content-Type"] = "application/octet-stream"
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    response["Content-Security-Policy"] = "default-src 'none'; sandbox"
    response["Referrer-Policy"] = "no-referrer"
    return response
