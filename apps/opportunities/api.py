import json
from functools import wraps
from datetime import datetime

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import F, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from apps.accounts.models import RoleAssignment
from apps.academics.models import AcademicPeriod, Career, Course, Enrollment
from apps.accounts.permissions import visible_course_enrollments
from apps.audit.services import record_event
from .models import Application, EligibilitySnapshot, Opportunity, OpportunityRequirement, OpportunityVersion
from .services import can_manage_version, decide_application, evaluate_eligibility, has_career_role


def login_required_json(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({"detail": "Inicia sesión para consultar o gestionar oportunidades."}, status=403)
        return view(request, *args, **kwargs)
    return wrapped


def _body(request):
    try:
        return json.loads(request.body or "{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise ValidationError("El cuerpo JSON no es válido.")


def _error(exc, status=400):
    messages = exc.messages if isinstance(exc, ValidationError) else [str(exc)]
    return JsonResponse({"detail": " ".join(messages)}, status=status)


def _version_payload(version, *, enrollment=None, include_applications=False):
    data = {
        "id": str(version.opportunity_id), "versionId": str(version.pk), "version": version.version_number,
        "title": version.title, "kind": version.kind, "kindLabel": version.get_kind_display(),
        "description": version.description, "benefits": version.benefits,
        "instructions": version.application_instructions, "opensAt": version.opens_at.isoformat(),
        "closesAt": version.closes_at.isoformat(), "capacity": version.capacity,
        "status": version.opportunity.status, "publishedAt": version.published_at.isoformat() if version.published_at else None,
        "careers": list(version.careers.values("id", "code", "name")),
        "requirements": [{"id": str(r.pk), "field": r.field_code, "label": r.display_label,
                          "operator": r.operator, "target": str(r.target_number) if r.target_number is not None else None,
                          "courseCode": r.course_code, "periodCode": r.academic_period_code} for r in version.requirements.all()],
    }
    if enrollment:
        evaluation = evaluate_eligibility(version, enrollment)
        data["eligibility"] = {"id": str(evaluation.pk), "overall": evaluation.overall_status,
                               "computedAt": evaluation.computed_at.isoformat(), "requirements": evaluation.results}
    if include_applications:
        data["applications"] = [_application_payload(a, refresh=True) for a in version.applications.select_related(
            "enrollment__student__user", "enrollment__career", "enrollment__period", "eligibility",
        ).prefetch_related("decisions__actor").order_by("submitted_at")]
    return data


def _application_payload(application, *, refresh=False):
    student = application.enrollment.student
    latest = application.decisions.order_by("-decided_at").first()
    last_decision_results = latest.resolution_eligibility.results if latest and latest.resolution_eligibility_id else application.eligibility.results
    live_evaluation = evaluate_eligibility(application.version, application.enrollment, persist=False) if refresh else None
    current_results = live_evaluation.results if live_evaluation else last_decision_results
    current_version = application.version.opportunity.active_version
    return {
        "id": str(application.pk), "status": application.status, "statusLabel": application.get_status_display(),
        "versionId": str(application.version_id), "title": application.version.title,
        "newVersionId": str(current_version.pk) if current_version and current_version.pk != application.version_id else None,
        "newVersionTitle": current_version.title if current_version and current_version.pk != application.version_id else None,
        "submittedAt": application.submitted_at.isoformat(), "student": student.user.get_full_name(),
        "studentNumber": student.student_number, "career": application.enrollment.career.code,
        "period": application.enrollment.period.code,
        "initialEligibility": application.eligibility.results,
        "initialOverall": application.eligibility.overall_status,
        "currentEligibility": current_results,
        "eligibilityChanged": current_results != last_decision_results,
        "latestDecision": ({"decision": latest.decision, "reason": latest.reason, "actor": latest.actor.get_full_name(),
                            "at": latest.decided_at.isoformat(), "previousStatus": latest.previous_status} if latest else None),
    }


def _authorized_careers(user):
    if user.is_superuser:
        return Career.objects.filter(active=True)
    today = timezone.localdate()
    assignments = user.role_assignments.filter(active=True, starts_at__lte=today).filter(
        Q(ends_at__isnull=True) | Q(ends_at__gte=today)
    )
    if assignments.filter(scope=RoleAssignment.Scope.INSTITUTION, role=RoleAssignment.Role.INSTITUTION_ADMIN).exists():
        return Career.objects.filter(active=True, institution__in=assignments.values("institution_id"))
    return Career.objects.filter(active=True, pk__in=assignments.filter(
        scope=RoleAssignment.Scope.CAREER,
        role__in=(RoleAssignment.Role.COORDINATOR, RoleAssignment.Role.CAREER_ADMIN),
    ).values("career_id"))


def _validate_criteria(version, requirements):
    if not isinstance(requirements, list) or not requirements:
        raise ValidationError("Define al menos un requisito tipado.")
    if len(requirements) > 12:
        raise ValidationError("Una convocatoria admite hasta 12 requisitos.")
    allowed = {field for field, _ in OpportunityRequirement.Field.choices}
    for index, row in enumerate(requirements):
        if not isinstance(row, dict) or row.get("field") not in allowed:
            raise ValidationError(f"El requisito {index + 1} utiliza un campo no permitido.")
        field = row["field"]
        label = str(row.get("label", "")).strip()
        if not label or len(label) > 180:
            raise ValidationError(f"El requisito {index + 1} necesita una etiqueta (máximo 180 caracteres).")
        target = row.get("target")
        course_code = str(row.get("courseCode", "")).strip().upper()
        numeric_fields = {"average", "own_points", "semester"}
        period_code = str(row.get("periodCode", "")).strip().upper()
        item = OpportunityRequirement(
            version=version, field_code=field,
            operator=OpportunityRequirement.Operator.GTE if field in numeric_fields else OpportunityRequirement.Operator.EXACT if field == "period" else OpportunityRequirement.Operator.EXISTS,
            target_number=target if field in numeric_fields else None,
            course_code=course_code if field == "approved_course" else "",
            academic_period_code=period_code if field == "period" else "",
            display_label=label, sort_order=index,
        )
        item.full_clean()
        career_ids = set(version.careers.values_list("pk", flat=True))
        course_careers = set(Course.objects.filter(career_id__in=career_ids, code=course_code).values_list("career_id", flat=True))
        if field == "approved_course" and career_ids - course_careers:
            raise ValidationError(f"El curso {course_code} debe existir en todas las carreras seleccionadas.")
        period_careers = set(AcademicPeriod.objects.filter(career_id__in=career_ids, code=period_code).values_list("career_id", flat=True))
        if field == "period" and career_ids - period_careers:
            raise ValidationError(f"El periodo {period_code} debe existir en todas las carreras seleccionadas.")
        if field == "average" and target is not None and float(target) > 100:
            raise ValidationError("El promedio debe estar dentro de la escala de la carrera (máximo 100 en esta versión).")
        item.save()


def _create_version(opportunity, actor, data, version_number, publish=False):
    required = ("title", "kind", "description", "opensAt", "closesAt", "capacity")
    if any(not data.get(field) for field in required):
        raise ValidationError("Completa título, tipo, descripción, fechas y cupos.")
    career_ids = data.get("careerIds") or []
    careers = _authorized_careers(actor).filter(pk__in=career_ids)
    if not careers.exists() or careers.count() != len(set(career_ids)):
        raise PermissionDenied("Solo puedes convocar carreras de tu ámbito.")
    try:
        opens_at = datetime.fromisoformat(data["opensAt"].replace("Z", "+00:00"))
        closes_at = datetime.fromisoformat(data["closesAt"].replace("Z", "+00:00"))
        if timezone.is_naive(opens_at) or timezone.is_naive(closes_at):
            raise ValueError
        capacity = int(data["capacity"])
    except (ValueError, TypeError):
        raise ValidationError("Usa fechas con zona horaria válida y cupos enteros positivos.")
    if closes_at <= opens_at or capacity < 1 or capacity > 10000:
        raise ValidationError("El cierre debe ser posterior a la apertura; cupos entre 1 y 10000.")
    version = OpportunityVersion.objects.create(
        opportunity=opportunity, version_number=version_number,
        title=str(data["title"]).strip(), kind=data["kind"],
        description=str(data["description"]).strip(), benefits=str(data.get("benefits", "")).strip(),
        application_instructions=str(data.get("instructions", "")).strip(),
        opens_at=opens_at, closes_at=closes_at, capacity=capacity,
    )
    version.careers.set(careers)
    _validate_criteria(version, data.get("requirements"))
    if publish:
        _publish(version, actor)
    return version


def _publish(version, actor):
    if not can_manage_version(actor, version):
        raise PermissionDenied("No tienes permiso para publicar esta convocatoria.")
    if version.opens_at >= version.closes_at or version.capacity < 1 or not version.requirements.exists():
        raise ValidationError("La convocatoria necesita fechas válidas, cupo positivo y requisitos.")
    version.published_at = timezone.now()
    version.published_by = actor
    version.save(update_fields=("published_at", "published_by"))
    version.opportunity.status = Opportunity.Status.PUBLISHED
    version.opportunity.active_version = version
    version.opportunity.save(update_fields=("status", "active_version", "updated_at"))
    first_career = version.careers.order_by("pk").first()
    if first_career:
        record_event(actor=actor, action="opportunity.published", obj=version,
                     scope_type="career", scope_id=first_career.pk,
                     reason="Publicación de convocatoria versionada",
                     safe_metadata={"version": version.version_number, "careerCount": version.careers.count()})


@login_required_json
@require_GET
def api_opportunities(request):
    user = request.user
    enrollments = Enrollment.objects.filter(student__user=user, status=Enrollment.Status.ACTIVE).select_related("career", "period")
    enrollment_ids = list(enrollments.values_list("id", flat=True))
    career_ids = set(enrollments.values_list("career_id", flat=True))
    # Teaching staff can discover calls offered to the careers of their active groups.
    # This grants read-only visibility; application and eligibility still require a student enrollment.
    career_ids.update(visible_course_enrollments(user).values_list("offering__course__career_id", flat=True))
    versions = OpportunityVersion.objects.filter(
        opportunity__status__in=(Opportunity.Status.PUBLISHED, Opportunity.Status.CLOSED),
        opportunity__active_version_id=F("pk"),
        careers__id__in=career_ids,
    ).select_related("opportunity").prefetch_related("careers", "requirements").distinct()
    opportunities = [_version_payload(v) for v in versions]
    my_applications = Application.objects.filter(enrollment_id__in=enrollment_ids).select_related("version__opportunity", "eligibility", "enrollment__career")
    staff_versions = OpportunityVersion.objects.select_related("opportunity").prefetch_related("careers", "requirements")
    staff = [_version_payload(v, include_applications=True) for v in staff_versions if can_manage_version(user, v)]
    own = [{"id": str(e.pk), "career": e.career.code, "careerName": e.career.name, "period": e.period.code,
            "periodName": e.period.name, "semester": e.semester_number} for e in enrollments]
    careers = _authorized_careers(user)
    periods = AcademicPeriod.objects.filter(career__in=careers).select_related("career").values(
        "id", "code", "name", "career__code",
    )
    return JsonResponse({"opportunities": opportunities, "enrollments": own,
                         "applications": [_application_payload(a) for a in my_applications], "managed": staff,
                         "careers": [{"id": str(c.pk), "code": c.code, "name": c.name} for c in careers],
                         "periods": [{"id": str(p["id"]), "code": p["code"], "name": p["name"], "career": p["career__code"]} for p in periods]})


@login_required_json
@require_POST
def api_create_opportunity(request):
    try:
        data = _body(request)
        career_ids = data.get("careerIds") or []
        careers = _authorized_careers(request.user).filter(pk__in=career_ids)
        if not careers.exists() or careers.count() != len(set(career_ids)):
            raise PermissionDenied("Se requiere coordinación o administración en la carrera elegida.")
        with transaction.atomic():
            opportunity = Opportunity.objects.create(owner=request.user, created_by=request.user)
            version = _create_version(opportunity, request.user, data, 1, publish=data.get("publish") is True)
        return JsonResponse(_version_payload(version), status=201)
    except PermissionDenied as exc:
        return _error(exc, 403)
    except ValidationError as exc:
        return _error(exc)


@login_required_json
@require_POST
def api_new_version(request, opportunity_id):
    try:
        with transaction.atomic():
            opportunity = get_object_or_404(Opportunity.objects.select_for_update(), pk=opportunity_id)
            latest = opportunity.versions.prefetch_related("careers").first()
            if latest and not can_manage_version(request.user, latest):
                raise PermissionDenied("Solo el responsable asignado puede crear una nueva versión.")
            if not latest and opportunity.owner_id != request.user.pk and not request.user.is_superuser:
                raise PermissionDenied("Solo el responsable asignado puede crear una nueva versión.")
            next_version = (opportunity.versions.order_by("-version_number").values_list("version_number", flat=True).first() or 0) + 1
            version = _create_version(opportunity, request.user, _body(request), next_version, publish=True)
        return JsonResponse(_version_payload(version), status=201)
    except PermissionDenied as exc:
        return _error(exc, 403)
    except ValidationError as exc:
        return _error(exc)


@login_required_json
@require_POST
def api_publish(request, version_id):
    try:
        with transaction.atomic():
            version_ref = get_object_or_404(OpportunityVersion.objects.only("pk", "opportunity_id"), pk=version_id)
            opportunity = get_object_or_404(Opportunity.objects.select_for_update(), pk=version_ref.opportunity_id)
            version = get_object_or_404(OpportunityVersion.objects.select_for_update().prefetch_related("careers", "requirements"), pk=version_id)
            version.opportunity = opportunity
            _publish(version, request.user)
        return JsonResponse({"status": version.opportunity.status})
    except PermissionDenied as exc:
        return _error(exc, 403)
    except ValidationError as exc:
        return _error(exc)


@login_required_json
@require_POST
def api_close_opportunity(request, opportunity_id):
    try:
        data = _body(request)
        action = data.get("action", "close")
        reason = str(data.get("reason", "")).strip()
        if action not in {"close", "cancel"}:
            raise ValidationError("Acción de cierre inválida.")
        if len(reason) < 5:
            raise ValidationError("Registra un motivo de al menos cinco caracteres para cerrar o cancelar la convocatoria.")
        with transaction.atomic():
            opportunity = get_object_or_404(Opportunity.objects.select_for_update(), pk=opportunity_id)
            latest = opportunity.versions.prefetch_related("careers").first()
            if latest is None or not can_manage_version(request.user, latest):
                raise PermissionDenied("No tienes permiso para gestionar esta convocatoria.")
            if opportunity.status != Opportunity.Status.PUBLISHED:
                raise ValidationError("Solo una convocatoria publicada puede cerrarse o cancelarse.")
            opportunity.status = Opportunity.Status.CLOSED if action == "close" else Opportunity.Status.CANCELLED
            opportunity.save(update_fields=("status", "updated_at"))
            career_id = latest.careers.order_by("pk").values_list("pk", flat=True).first()
            record_event(actor=request.user, action=f"opportunity.{opportunity.status}", obj=opportunity,
                         scope_type="career", scope_id=career_id, reason=reason,
                         safe_metadata={"version": latest.version_number})
            if action == "close" and not Application.objects.filter(
                version__opportunity=opportunity,
                status__in=(Application.Status.SUBMITTED, Application.Status.IN_REVIEW),
            ).exists():
                opportunity.status = Opportunity.Status.RESOLVED
                opportunity.save(update_fields=("status", "updated_at"))
                record_event(actor=request.user, action="opportunity.resolved", obj=opportunity,
                             scope_type="career", scope_id=career_id,
                             reason="Convocatoria cerrada sin postulaciones pendientes",
                             safe_metadata={"version": latest.version_number})
        return JsonResponse({"status": opportunity.status})
    except PermissionDenied as exc:
        return _error(exc, 403)
    except ValidationError as exc:
        return _error(exc)


@login_required_json
@require_POST
def api_check_eligibility(request, version_id):
    try:
        data = _body(request)
        version = get_object_or_404(OpportunityVersion.objects.prefetch_related("careers", "requirements"), pk=version_id, published_at__isnull=False)
        enrollment = get_object_or_404(Enrollment.objects.select_related("career", "period"), pk=data.get("enrollmentId"), student__user=request.user, status=Enrollment.Status.ACTIVE)
        result = evaluate_eligibility(version, enrollment)
        return JsonResponse({"id": str(result.pk), "overall": result.overall_status, "computedAt": result.computed_at.isoformat(), "requirements": result.results})
    except PermissionDenied as exc:
        return _error(exc, 403)


@login_required_json
@require_POST
def api_apply(request, version_id):
    try:
        data = _body(request)
        with transaction.atomic():
            version_ref = get_object_or_404(OpportunityVersion.objects.only("pk", "opportunity_id"), pk=version_id, published_at__isnull=False)
            opportunity = get_object_or_404(Opportunity.objects.select_for_update(), pk=version_ref.opportunity_id)
            version = get_object_or_404(OpportunityVersion.objects.select_for_update().prefetch_related("careers", "requirements"), pk=version_id, published_at__isnull=False)
            version.opportunity = opportunity
            now = timezone.now()
            if version.opportunity.status != Opportunity.Status.PUBLISHED or version.opportunity.active_version_id != version.pk or not version.opens_at <= now <= version.closes_at:
                raise ValidationError("La convocatoria no está abierta para postulaciones.")
            enrollment = get_object_or_404(Enrollment.objects.select_related("career", "period"), pk=data.get("enrollmentId"), student__user=request.user, status=Enrollment.Status.ACTIVE)
            if Application.objects.filter(version=version, enrollment=enrollment).exclude(status=Application.Status.WITHDRAWN).exists():
                raise ValidationError("Ya tienes una postulación activa para esta versión.")
            snapshot = evaluate_eligibility(version, enrollment)
            if snapshot.overall_status != EligibilitySnapshot.Overall.ELIGIBLE:
                raise ValidationError("Solo se puede postular cuando todos los requisitos tienen datos verificados y se cumplen.")
            application = Application.objects.create(version=version, enrollment=enrollment, eligibility=snapshot)
            record_event(actor=request.user, action="opportunity.application_submitted", obj=application,
                         scope_type="career", scope_id=enrollment.career_id,
                         reason="Postulación a convocatoria abierta",
                         safe_metadata={"version": version.version_number, "eligibility": snapshot.overall_status})
        return JsonResponse(_application_payload(application), status=201)
    except PermissionDenied as exc:
        return _error(exc, 403)
    except ValidationError as exc:
        return _error(exc)


@login_required_json
@require_POST
def api_withdraw(request, application_id):
    application = get_object_or_404(Application.objects.select_related("enrollment__student", "version"), pk=application_id, enrollment__student__user=request.user)
    if application.status not in {Application.Status.SUBMITTED, Application.Status.IN_REVIEW} or timezone.now() > application.version.closes_at:
        return JsonResponse({"detail": "Solo puedes retirar una postulación sin resolver antes del cierre."}, status=400)
    application.status = Application.Status.WITHDRAWN
    application.withdrawn_at = timezone.now()
    application.save(update_fields=("status", "withdrawn_at"))
    record_event(actor=request.user, action="opportunity.application_withdrawn", obj=application,
                 scope_type="career", scope_id=application.enrollment.career_id,
                 reason="Retiro de postulación por el estudiante",
                 safe_metadata={"version": application.version.version_number})
    return JsonResponse({"status": application.status})


@login_required_json
@require_POST
def api_decide(request, application_id):
    try:
        data = _body(request)
        application = decide_application(actor=request.user, application_id=application_id,
                                         decision=data.get("decision", ""), reason=data.get("reason", ""))
        return JsonResponse(_application_payload(application))
    except PermissionDenied as exc:
        return _error(exc, 403)
    except ValidationError as exc:
        return _error(exc)
