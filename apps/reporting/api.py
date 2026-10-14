import csv
from datetime import datetime
from decimal import Decimal

from django.db.models import Avg, Count, DecimalField, ExpressionWrapper, F, Q, Sum, Value
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.accounts.models import RoleAssignment, User
from apps.accounts.permissions import current_role_assignments, visible_course_enrollments
from apps.academics.models import AcademicPeriod, Career, Course, CourseEnrollment, CourseOffering, Enrollment, GradeRecord, StudentProfile
from apps.activities.models import Activity, PointsMovement
from apps.audit.models import AuditEvent
from apps.opportunities.models import Application, Opportunity
from apps.support.models import SupportCase
from apps.transfers.models import TransferRequest
from .models import Notification


def manageable_careers(user):
    if user.is_superuser:
        return Career.objects.filter(active=True)
    roles = current_role_assignments(user)
    career_ids = roles.filter(scope="career", role__in=(RoleAssignment.Role.COORDINATOR, RoleAssignment.Role.CAREER_ADMIN)).values("career_id")
    institution_ids = roles.filter(scope="institution", role=RoleAssignment.Role.INSTITUTION_ADMIN).values("institution_id")
    return Career.objects.filter(active=True).filter(Q(pk__in=career_ids) | Q(institution_id__in=institution_ids)).distinct()


def _report_rows(career, period):
    enrollments = Enrollment.objects.filter(career=career)
    activities = Activity.objects.filter(enrollment__career=career)
    points = PointsMovement.objects.filter(enrollment__career=career)
    grades = GradeRecord.objects.filter(enrollment__career=career, status=GradeRecord.Status.VERIFIED, supersedes__isnull=True)
    applications = Application.objects.filter(enrollment__career=career)
    transfers = TransferRequest.objects.filter(sender__career=career)
    cases = SupportCase.objects.filter(alert__enrollment__career=career)
    if period:
        enrollments = enrollments.filter(period=period)
        activities = activities.filter(enrollment__period=period)
        points = points.filter(enrollment__period=period)
        grades = grades.filter(enrollment__period=period)
        applications = applications.filter(enrollment__period=period)
        transfers = transfers.filter(sender__period=period)
        cases = cases.filter(alert__period=period)
    active_enrollments = enrollments.filter(status=Enrollment.Status.ACTIVE)
    opportunities = Opportunity.objects.filter(status=Opportunity.Status.PUBLISHED, active_version__careers=career)
    if period:
        opportunities = opportunities.filter(active_version__opens_at__date__lte=period.ends_on, active_version__closes_at__date__gte=period.starts_on)
    return [
        ("Matrículas activas", active_enrollments.count(), "Personas matriculadas en estado activo", active_enrollments.count()),
        ("Matrículas concluidas", enrollments.filter(status=Enrollment.Status.COMPLETED).count(), "Matrículas con estado concluida", enrollments.count()),
        ("Matrículas retiradas o canceladas", enrollments.filter(status__in=(Enrollment.Status.WITHDRAWN, Enrollment.Status.CANCELLED)).count(), "Matrículas retiradas o canceladas", enrollments.count()),
        ("Grupos con matrícula", CourseEnrollment.objects.filter(enrollment__in=active_enrollments, active=True).values("offering_id").distinct().count(), "Grupos distintos con matrículas activas", active_enrollments.count()),
        ("Notas verificadas", grades.count(), "Registros de nota verificados vigentes", grades.count()),
        ("Promedio verificado / 100", round(float(grades.annotate(normalized=ExpressionWrapper(
            F("grade_value") * Value(Decimal("100")) / F("scale_snapshot"),
            output_field=DecimalField(max_digits=8, decimal_places=2),
        )).aggregate(v=Avg("normalized"))["v"] or 0), 2) if grades.exists() else "—",
         "Promedio de notas verificadas normalizadas a escala 100", grades.count()),
        ("Evidencias aprobadas", activities.filter(status=Activity.Status.APPROVED).count(), "Evidencias con estado aprobada", activities.count()),
        ("Evidencias pendientes", activities.filter(status__in=(Activity.Status.IN_REVIEW, Activity.Status.OBSERVED)).count(), "En revisión u observadas", activities.count()),
        ("Evidencias rechazadas o revocadas", activities.filter(status__in=(Activity.Status.REJECTED, Activity.Status.REVOKED)).count(), "Evidencias rechazadas o revocadas", activities.count()),
        ("Puntos SPD", points.aggregate(v=Sum("points"))["v"] or 0, "Suma neta de movimientos SPD", points.count()),
        ("Oportunidades publicadas", opportunities.values("pk").distinct().count(), "Oportunidades vigentes dirigidas a la carrera", opportunities.count()),
        ("Postulaciones", applications.count(), "Postulaciones registradas", applications.count()),
        ("Postulaciones en revisión", applications.filter(status__in=(Application.Status.SUBMITTED, Application.Status.IN_REVIEW)).count(), "Postulaciones pendientes de resolución", applications.count()),
        ("Postulaciones seleccionadas", applications.filter(status=Application.Status.SELECTED).count(), "Postulaciones seleccionadas mediante decisión humana", applications.count()),
        ("Solicitudes de transferencia", transfers.count(), "Solicitudes de transferencia enviadas desde la carrera", transfers.count()),
        ("Transferencias pendientes", transfers.filter(status__in=(TransferRequest.Status.IN_REVIEW, TransferRequest.Status.FLAGGED)).count(), "Solicitudes en revisión o revisión prioritaria", transfers.count()),
        ("Transferencias aprobadas", transfers.filter(status=TransferRequest.Status.APPROVED).count(), "Solicitudes aprobadas", transfers.count()),
        ("Casos de acompañamiento abiertos", cases.filter(status__in=(SupportCase.Status.OPEN, SupportCase.Status.IN_PROGRESS)).count(), "Casos abiertos o en seguimiento", cases.count()),
    ]


def _personal_report(user):
    """A self-only summary for students without administrative report grants."""
    enrollments = Enrollment.objects.filter(student__user=user)
    grades = GradeRecord.objects.filter(enrollment__in=enrollments, status=GradeRecord.Status.VERIFIED, supersedes__isnull=True)
    activities = Activity.objects.filter(enrollment__in=enrollments)
    points = PointsMovement.objects.filter(enrollment__in=enrollments)
    applications = Application.objects.filter(enrollment__in=enrollments)
    transfers = TransferRequest.objects.filter(Q(sender__in=enrollments) | Q(recipient__in=enrollments))
    cases = SupportCase.objects.filter(alert__enrollment__in=enrollments)
    grade_average = grades.annotate(normalized=ExpressionWrapper(
        F("grade_value") * Value(Decimal("100")) / F("scale_snapshot"),
        output_field=DecimalField(max_digits=8, decimal_places=2),
    )).aggregate(v=Avg("normalized"))["v"]
    rows = [
        ("Mis matrículas activas", enrollments.filter(status=Enrollment.Status.ACTIVE).count(), "Matrículas propias con estado activo", enrollments.count()),
        ("Mis periodos concluidos", enrollments.filter(status=Enrollment.Status.COMPLETED).count(), "Matrículas propias con periodo concluido", enrollments.count()),
        ("Mis notas verificadas", grades.count(), "Registros verificados y vigentes de tus matrículas", grades.count()),
        ("Mi promedio verificado / 100", round(float(grade_average), 2) if grade_average is not None else "—", "Promedio de tus notas verificadas normalizadas a escala 100", grades.count()),
        ("Mis evidencias aprobadas", activities.filter(status=Activity.Status.APPROVED).count(), "Evidencias propias aprobadas", activities.count()),
        ("Mis evidencias en revisión", activities.filter(status__in=(Activity.Status.IN_REVIEW, Activity.Status.OBSERVED)).count(), "Evidencias propias en revisión u observadas", activities.count()),
        ("Mi saldo SPD", points.aggregate(v=Sum("points"))["v"] or 0, "Saldo neto de tus movimientos SPD", points.count()),
        ("Mis postulaciones", applications.count(), "Postulaciones propias registradas", applications.count()),
        ("Mis transferencias", transfers.count(), "Solicitudes donde participas como remitente o destinatario", transfers.count()),
        ("Mi acompañamiento", cases.count(), "Casos de acompañamiento vinculados a tus matrículas", cases.count()),
    ]
    return [{"career": "Mi trayectoria", "careerCode": "PERSONAL", "metric": name, "value": value,
             "definition": definition, "denominator": denominator} for name, value, definition, denominator in rows]


def _report_charts(career, period=None):
    enrollments = Enrollment.objects.filter(career=career)
    activities = Activity.objects.filter(enrollment__career=career)
    applications = Application.objects.filter(enrollment__career=career)
    if period:
        enrollments = enrollments.filter(period=period)
        activities = activities.filter(enrollment__period=period)
        applications = applications.filter(enrollment__period=period)
    periods = list(AcademicPeriod.objects.filter(career=career).order_by("starts_on"))
    activity = list(activities.values("enrollment__period_id").annotate(total=Count("pk")))
    application = list(applications.values("enrollment__period_id").annotate(total=Count("pk")))
    activity_by_period = {str(row["enrollment__period_id"]): row["total"] for row in activity}
    applications_by_period = {str(row["enrollment__period_id"]): row["total"] for row in application}
    evidence_statuses = [{"label": label, "value": activities.filter(status=value).count()}
                         for value, label in Activity.Status.choices]
    opportunities = Opportunity.objects.filter(active_version__careers=career)
    if period:
        opportunities = opportunities.filter(active_version__opens_at__date__lte=period.ends_on,
                                             active_version__closes_at__date__gte=period.starts_on)
    opportunity_statuses = [{"label": label, "value": opportunities.filter(status=value).distinct().count()}
                            for value, label in Opportunity.Status.choices]
    balance = enrollments.values("pk").annotate(total=Sum("spd_movements__points"))
    levels = ((0, 99, "Explorador"), (100, 249, "Participante"), (250, 499, "Desarrollador"),
              (500, 749, "Líder"), (750, None, "Talento destacado"))
    totals = [0] * len(levels)
    for row in balance:
        score = row["total"] or 0
        for index, (lower, upper, _) in enumerate(levels):
            if score >= lower and (upper is None or score <= upper):
                totals[index] += 1
                break
    return {
        "activityByPeriod": [{"label": p.code, "detail": p.name, "value": activity_by_period.get(str(p.pk), 0)} for p in periods],
        "pointsDistribution": [{"label": level[2], "value": totals[index]} for index, level in enumerate(levels)],
        "evidenceStatuses": evidence_statuses,
        "opportunityStatuses": opportunity_statuses,
        "applicationsByPeriod": [{"label": p.code, "detail": p.name, "value": applications_by_period.get(str(p.pk), 0)} for p in periods],
    }


def _teacher_group_report(user):
    """Aggregate only the active rosters attached to groups visible to this teacher."""
    roster = visible_course_enrollments(user).select_related(
        "enrollment__career", "enrollment__period", "offering__course", "offering__period",
    ).distinct()
    if not roster.exists():
        return None
    enrollment_ids = roster.values("enrollment_id").distinct()
    offering_ids = roster.values("offering_id").distinct()
    enrollments = Enrollment.objects.filter(pk__in=enrollment_ids)
    offerings = CourseOffering.objects.filter(pk__in=offering_ids).distinct()
    periods = list(AcademicPeriod.objects.filter(pk__in=offerings.values("period_id")).distinct().order_by("starts_on"))
    activities = Activity.objects.filter(enrollment_id__in=enrollment_ids)
    grades = GradeRecord.objects.filter(enrollment_id__in=enrollment_ids, status=GradeRecord.Status.VERIFIED, supersedes__isnull=True)
    points = PointsMovement.objects.filter(enrollment_id__in=enrollment_ids)
    applications = Application.objects.filter(enrollment_id__in=enrollment_ids)
    transfers = TransferRequest.objects.filter(sender_id__in=enrollment_ids)
    cases = SupportCase.objects.filter(assigned_to=user, alert__enrollment_id__in=enrollment_ids)
    average = grades.annotate(normalized=ExpressionWrapper(
        F("grade_value") * Value(Decimal("100")) / F("scale_snapshot"),
        output_field=DecimalField(max_digits=8, decimal_places=2),
    )).aggregate(value=Avg("normalized"))["value"]

    rows = [
        ("Grupos asignados", offerings.count(), "Grupos activos visibles para esta cuenta docente", offerings.count()),
        ("Matrículas activas en grupos", enrollments.count(), "Matrículas únicas activas en los grupos asignados", enrollments.count()),
        ("Notas verificadas", grades.count(), "Notas vigentes verificadas en las matrículas visibles", grades.count()),
        ("Promedio verificado / 100", round(float(average), 2) if average is not None else "—", "Promedio de notas visibles normalizadas a escala 100", grades.count()),
        ("Evidencias aprobadas", activities.filter(status=Activity.Status.APPROVED).count(), "Evidencias aprobadas de matrículas visibles", activities.count()),
        ("Evidencias por revisar", activities.filter(status__in=(Activity.Status.IN_REVIEW, Activity.Status.OBSERVED)).count(), "Evidencias en revisión u observadas dentro del alcance docente", activities.count()),
        ("Puntos SPD", points.aggregate(value=Sum("points"))["value"] or 0, "Puntos acumulados en las matrículas visibles", points.count()),
        ("Postulaciones de estudiantes", applications.count(), "Postulaciones de matrículas presentes en grupos asignados", applications.count()),
        ("Transferencias pendientes", transfers.filter(status__in=(TransferRequest.Status.IN_REVIEW, TransferRequest.Status.FLAGGED)).count(), "Solicitudes enviadas por matrículas visibles que requieren revisión", transfers.count()),
        ("Casos asignados", cases.count(), "Casos de acompañamiento confiados a esta cuenta docente y dentro de sus grupos", cases.count()),
    ]
    career = roster.first().offering.course.career
    balance_rows = enrollments.values("pk").annotate(total=Sum("spd_movements__points"))
    levels = ((0, 99, "Explorador"), (100, 249, "Participante"), (250, 499, "Desarrollador"),
              (500, 749, "Líder"), (750, None, "Talento destacado"))
    level_totals = [0] * len(levels)
    for row in balance_rows:
        score = row["total"] or 0
        for index, (lower, upper, _label) in enumerate(levels):
            if score >= lower and (upper is None or score <= upper):
                level_totals[index] += 1
                break
    charts = [{
        "career": career.name, "careerCode": career.code,
        "activityByPeriod": [{"label": period.code, "detail": period.name,
                              "value": activities.filter(enrollment__period=period).count()} for period in periods],
        "pointsDistribution": [{"label": level[2], "value": level_totals[index]} for index, level in enumerate(levels)],
        "evidenceStatuses": [{"label": label, "value": activities.filter(status=value).count()}
                             for value, label in Activity.Status.choices],
        "opportunityStatuses": [{"label": label, "value": applications.filter(status=value).count()}
                                for value, label in Application.Status.choices],
        "applicationsByPeriod": [{"label": period.code, "detail": period.name,
                                  "value": applications.filter(enrollment__period=period).count()} for period in periods],
    }]
    return {
        "canManage": False, "groupView": True, "personalView": False, "careers": [], "periods": [],
        "selectedPeriod": "", "rows": [{"career": career.name, "careerCode": career.code,
                                           "metric": name, "value": value, "definition": definition,
                                           "denominator": denominator}
                                          for name, value, definition, denominator in rows],
        "charts": charts,
        "source": "Datos agregados de matrículas en tus grupos asignados, notas verificadas, evidencias, SPD, postulaciones, transferencias y casos confiados a tu cuenta.",
        "extractedAt": timezone.localtime().isoformat(timespec="seconds"),
    }


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def api_report(request):
    careers = manageable_careers(request.user)
    available_careers = list(careers)
    requested = request.query_params.get("career")
    if requested:
        career = careers.filter(pk=requested).first()
        if not career:
            return Response({"detail": "No tienes acceso a esta carrera."}, status=status.HTTP_404_NOT_FOUND)
        selected = [career]
    else:
        selected = list(careers)
    if not selected:
        if request.query_params.get("career") or request.query_params.get("period"):
            return Response({"detail": "Tu rol no tiene acceso a informes de carrera."}, status=403)
        personal_rows = _personal_report(request.user)
        if Enrollment.objects.filter(student__user=request.user).exists():
            return Response({"canManage": False, "personalView": True, "careers": [], "periods": [], "rows": personal_rows,
                             "source": "Tus propias matrículas, notas verificadas, evidencias, movimientos SPD, postulaciones, transferencias y acompañamiento.",
                             "extractedAt": timezone.localtime().isoformat(timespec="seconds")})
        group_report = _teacher_group_report(request.user)
        if group_report:
            return Response(group_report)
        return Response({"canManage": False, "personalView": False, "careers": [], "periods": [], "rows": [],
                         "message": "Tu rol no tiene acceso a informes de carrera."})
    period_id = request.query_params.get("period")
    period = None
    if period_id:
        period = AcademicPeriod.objects.filter(pk=period_id, career__in=selected).first()
        if not period:
            return Response({"detail": "El periodo no pertenece a una carrera autorizada."}, status=status.HTTP_404_NOT_FOUND)
    rows = []
    charts = []
    for career in selected:
        if period and period.career_id != career.pk:
            continue
        for name, value, definition, denominator in _report_rows(career, period if period and period.career_id == career.pk else None):
            rows.append({"career": career.name, "careerCode": career.code, "metric": name, "value": value,
                         "definition": definition, "denominator": denominator})
        charts.append({"career": career.name, "careerCode": career.code,
                       **_report_charts(career, period if period and period.career_id == career.pk else None)})
    filters = {"career": str(selected[0].pk) if len(selected) == 1 else "", "period": str(period.pk) if period else ""}
    if request.query_params.get("export") == "csv":
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="upea-talent-informe.csv"'
        response.write("\ufeff")
        writer = csv.writer(response)
        writer.writerow(("Carrera", "Código", "Indicador", "Valor", "Definición", "Denominador", "Periodo", "Fecha de extracción"))
        extracted_at = timezone.localtime().isoformat(timespec="seconds")
        for row in rows:
            values = [row["career"], row["careerCode"], row["metric"], row["value"], row["definition"], row["denominator"], period.name if period else "Todos", extracted_at]
            safe_values = []
            for value in values:
                if isinstance(value, str) and value.lstrip(" \t\r\n").startswith(("=", "+", "-", "@")):
                    value = "'" + value
                safe_values.append(value)
            writer.writerow(safe_values)
        return response
    return Response({"canManage": True, "careers": [{"id": str(c.pk), "name": c.name, "code": c.code} for c in available_careers],
                     "periods": [{"id": str(p.pk), "name": p.name, "code": p.code, "careerId": str(p.career_id)} for p in AcademicPeriod.objects.filter(career__in=selected).order_by("-starts_on")],
                     "selectedPeriod": str(period.pk) if period else "", "rows": rows,
                     "charts": charts, "source": "Matrículas, notas verificadas, evidencias, movimientos SPD, oportunidades, postulaciones, transferencias y acompañamiento.",
                     "extractedAt": timezone.localtime().isoformat(timespec="seconds"), "filters": filters})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def api_audit(request):
    allowed = manageable_careers(request.user)
    if not allowed.exists():
        return Response({"detail": "No tienes permiso para consultar la bitácora."}, status=403)
    allowed_ids = [str(pk) for pk in allowed.values_list("pk", flat=True)]
    institution_ids = [str(pk) for pk in current_role_assignments(request.user).filter(
        scope="institution", role=RoleAssignment.Role.INSTITUTION_ADMIN,
    ).values_list("institution_id", flat=True)]
    rows = AuditEvent.objects.filter(
        Q(scope_type="career", scope_id__in=allowed_ids)
        | Q(scope_type="institution", scope_id__in=institution_ids)
    )
    rows = rows.exclude(action__startswith="demo.").exclude(
        Q(reason__icontains="fictic") | Q(reason__icontains="sintet") | Q(reason__icontains="demostraci")
    )
    if request.user.is_superuser:
        rows = AuditEvent.objects.all()
    career_id = request.query_params.get("career")
    if career_id:
        if not allowed.filter(pk=career_id).exists():
            return Response({"detail": "No tienes acceso a esta carrera."}, status=404)
        rows = rows.filter(scope_type="career", scope_id=career_id)
    action = request.query_params.get("action", "")[:80]
    if action:
        rows = rows.filter(action__icontains=action)
    start = request.query_params.get("from")
    end = request.query_params.get("to")
    try:
        if start:
            rows = rows.filter(occurred_at__date__gte=datetime.strptime(start, "%Y-%m-%d").date())
        if end:
            rows = rows.filter(occurred_at__date__lte=datetime.strptime(end, "%Y-%m-%d").date())
    except ValueError:
        return Response({"detail": "Usa fechas con formato AAAA-MM-DD."}, status=400)
    try:
        page = max(1, int(request.query_params.get("page", "1")))
        page_size = min(100, max(1, int(request.query_params.get("pageSize", "25"))))
    except ValueError:
        return Response({"detail": "La página y el tamaño deben ser números enteros."}, status=400)
    total = rows.count()
    if request.query_params.get("export") == "csv":
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="upea-talent-bitacora.csv"'
        response.write("\ufeff")
        writer = csv.writer(response)
        writer.writerow(("Fecha", "Actor", "Acción", "Tipo de objeto", "Identificador", "Ámbito", "Resultado", "Motivo"))
        for event in rows.select_related("actor").order_by("-occurred_at"):
            actor = event.actor.get_full_name() or event.actor.username if event.actor_id else "Proceso de autenticación"
            values = (timezone.localtime(event.occurred_at).isoformat(), actor, event.action, event.object_type,
                      event.object_id, f"{event.scope_type}:{event.scope_id}", event.result, event.reason)
            writer.writerow([("'" + value if isinstance(value, str) and value.lstrip(" \t\r\n").startswith(("=", "+", "-", "@")) else value)
                             for value in values])
        return response
    rows = rows.select_related("actor").order_by("-occurred_at")[(page - 1) * page_size:page * page_size]
    today = timezone.localdate()
    payload = []
    for event in rows:
        role_snapshot = event.safe_metadata.get("actorRoles", [])
        if not event.actor_id:
            role_scope = "Autenticación"
        elif isinstance(role_snapshot, list) and role_snapshot and all(
            isinstance(item, dict) and "role" in item and "scopeCode" in item for item in role_snapshot
        ):
            role_scope = ", ".join(f"{item['role']} · {item['scopeCode']}" for item in role_snapshot)
        elif event.actor.is_superuser:
            role_scope = "superuser · UPEA"
        else:
            roles = current_role_assignments(event.actor).filter(starts_at__lte=today).values_list("role", "scope", "career__code", "institution__short_name")
            role_scope = ", ".join(f"{role} · {career or institution or scope}" for role, scope, career, institution in roles) or "Sin asignación vigente"
        payload.append({"id": str(event.pk), "actor": (event.actor.get_full_name() or event.actor.username) if event.actor_id else "Intento de acceso",
                        "roleScope": role_scope,
                        "action": event.action, "objectType": event.object_type, "objectId": event.object_id,
                        "scope": f"{event.scope_type}:{event.scope_id}" if event.scope_id else "—", "result": event.result,
                        "reason": event.reason, "occurredAt": event.occurred_at.isoformat()})
    return Response({"events": payload, "page": page, "pageSize": page_size, "total": total,
                     "pages": (total + page_size - 1) // page_size, "readOnly": True})


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def api_academic_admin(request):
    careers = manageable_careers(request.user)
    if not careers.exists():
        return Response({"detail": "No tienes autorización para administrar carreras."}, status=403)
    if request.method == "GET":
        periods = AcademicPeriod.objects.filter(career__in=careers).select_related("career")
        courses = Course.objects.filter(career__in=careers).select_related("career")
        offerings = CourseOffering.objects.filter(course__career__in=careers).select_related("course", "period")
        students = StudentProfile.objects.filter(institution__in=careers.values("institution_id")).select_related("user", "institution")
        enrollments = Enrollment.objects.filter(career__in=careers).select_related("student__user", "period", "career")
        grade_careers = Career.objects.none() if not request.user.is_superuser else careers
        student_careers = Career.objects.none() if not request.user.is_superuser else careers
        if not request.user.is_superuser:
            roles = current_role_assignments(request.user)
            career_admin_ids = roles.filter(scope="career", role=RoleAssignment.Role.CAREER_ADMIN).values("career_id")
            institution_admin_ids = roles.filter(scope="institution", role=RoleAssignment.Role.INSTITUTION_ADMIN).values("institution_id")
            grade_careers = careers.filter(pk__in=career_admin_ids)
            student_careers = careers.filter(Q(pk__in=career_admin_ids) | Q(institution_id__in=institution_admin_ids))
        return Response({
            "careers": [{"id": str(c.pk), "code": c.code, "name": c.name, "institutionId": str(c.institution_id)} for c in careers],
            "gradeCareerIds": [str(pk) for pk in grade_careers.values_list("pk", flat=True)],
            "studentCareerIds": [str(pk) for pk in student_careers.values_list("pk", flat=True)],
            "periods": [{"id": str(p.pk), "careerId": str(p.career_id), "careerCode": p.career.code, "code": p.code, "name": p.name, "startsOn": p.starts_on.isoformat(), "endsOn": p.ends_on.isoformat(), "status": p.status} for p in periods],
            "courses": [{"id": str(c.pk), "careerId": str(c.career_id), "careerCode": c.career.code, "code": c.code, "name": c.name, "credits": c.credits, "active": c.active} for c in courses],
            "offerings": [{"id": str(o.pk), "courseId": str(o.course_id), "periodId": str(o.period_id), "label": f"{o.course.code} · {o.group_code} · {o.period.code}", "status": o.status} for o in offerings],
            "students": [{"id": str(s.pk), "institutionId": str(s.institution_id), "institution": s.institution.short_name, "studentNumber": s.student_number, "name": s.user.get_full_name() or s.user.username} for s in students],
            "enrollments": [{"id": str(e.pk), "careerId": str(e.career_id), "periodId": str(e.period_id), "studentId": str(e.student_id), "studentNumber": e.student.student_number, "student": e.student.user.get_full_name() or e.student.user.username, "semester": e.semester_number, "status": e.status} for e in enrollments],
        })
    from django.core.exceptions import ValidationError
    from django.db import transaction
    from apps.audit.services import record_event
    data = request.data
    kind = data.get("kind")
    career = careers.filter(pk=data.get("careerId")).first()
    if not career:
        return Response({"detail": "Selecciona una carrera dentro de tu ámbito."}, status=404)
    try:
        with transaction.atomic():
            if kind == "period":
                item = AcademicPeriod(career=career, code=data.get("code", "").strip(), name=data.get("name", "").strip(),
                    starts_on=data.get("startsOn"), ends_on=data.get("endsOn"), status=data.get("status", AcademicPeriod.Status.PLANNED),
                    grade_scale=data.get("gradeScale", 100), pass_threshold=data.get("passThreshold", 51))
                item.full_clean(); item.save(); action = "admin.period_created"
            elif kind == "course":
                item = Course(career=career, code=data.get("code", "").strip(), name=data.get("name", "").strip(), credits=data.get("credits", 0))
                item.full_clean(); item.save(); action = "admin.course_created"
            elif kind == "offering":
                course = Course.objects.filter(pk=data.get("courseId"), career=career).first()
                period = AcademicPeriod.objects.filter(pk=data.get("periodId"), career=career).first()
                if not course or not period:
                    return Response({"detail": "La asignatura y el periodo deben pertenecer a la carrera seleccionada."}, status=400)
                item = CourseOffering(course=course, period=period, group_code=data.get("groupCode", "").strip(), status=data.get("status", CourseOffering.Status.PLANNED))
                item.full_clean(); item.save(); action = "admin.offering_created"
            elif kind == "enrollment":
                student = StudentProfile.objects.filter(pk=data.get("studentId"), institution_id=career.institution_id).first()
                period = AcademicPeriod.objects.filter(pk=data.get("periodId"), career=career).first()
                if not student or not period:
                    return Response({"detail": "El estudiante y el periodo deben corresponder a la institución y carrera seleccionadas."}, status=400)
                item = Enrollment(student=student, career=career, period=period, semester_number=data.get("semester", 1),
                    status=data.get("status", Enrollment.Status.ACTIVE), valid_from=data.get("validFrom") or period.starts_on)
                item.full_clean(); item.save(); action = "admin.enrollment_created"
            elif kind == "student":
                from django.contrib.auth.password_validation import validate_password
                from apps.accounts.services import grant_role
                username = data.get("username", "").strip()
                email = data.get("email", "").strip()
                password = data.get("password", "")
                if not username or not email or not data.get("firstName", "").strip() or not data.get("lastName", "").strip():
                    return Response({"detail": "Completa usuario, correo, nombres y apellidos."}, status=400)
                account = User(username=username, email=email, first_name=data["firstName"].strip(), last_name=data["lastName"].strip())
                validate_password(password, user=account)
                account.set_password(password); account.full_clean(); account.save()
                item = StudentProfile(institution=career.institution, user=account, student_number=data.get("studentNumber", "").strip())
                item.full_clean(); item.save()
                grant_role(actor=request.user, user=account, role=RoleAssignment.Role.STUDENT,
                           scope=RoleAssignment.Scope.CAREER, career=career, reason="Alta académica en carrera")
                action = "admin.student_created"
            elif kind == "grade":
                from apps.profiles.services import create_grade_record
                enrollment = Enrollment.objects.filter(pk=data.get("enrollmentId"), career=career).select_related("period").first()
                offering = CourseOffering.objects.filter(pk=data.get("offeringId"), course__career=career).select_related("course", "period").first()
                if not enrollment or not offering:
                    return Response({"detail": "Selecciona matrícula y grupo válidos de la carrera."}, status=400)
                if enrollment.period_id != offering.period_id:
                    return Response({"detail": "La matrícula y el grupo deben corresponder al mismo periodo."}, status=400)
                item = create_grade_record(actor=request.user, enrollment=enrollment, offering=offering,
                    grade_value=data.get("gradeValue"), source=data.get("source", ""),
                    source_reference=data.get("sourceReference", ""), reason=data.get("reason", ""))
                action = None
            else:
                return Response({"detail": "Tipo de registro administrativo no reconocido."}, status=400)
            if action:
                record_event(actor=request.user, action=action, obj=item, scope_type="career", scope_id=career.pk,
                             reason=(data.get("reason") or "Registro mediante el panel de administración académica")[:300])
    except (ValidationError, ValueError, TypeError, AttributeError) as exc:
        errors = exc.message_dict if hasattr(exc, "message_dict") else {"detail": [str(exc)]}
        return Response({"errors": {key: [{"message": " ".join(value) if isinstance(value, list) else str(value)}] for key, value in errors.items()}}, status=400)
    return Response({"id": str(item.pk), "created": True}, status=201)


def _notification_payload(item):
    return {"id": str(item.pk), "kind": item.kind, "title": item.title, "message": item.message,
            "targetPath": item.target_path, "createdAt": item.created_at.isoformat(), "read": item.read_at is not None}


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def api_notifications(request):
    rows = Notification.objects.filter(recipient=request.user)
    return Response({"unreadCount": rows.filter(read_at__isnull=True).count(), "items": [_notification_payload(item) for item in rows[:50]]})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def api_mark_notification_read(request, notification_id):
    item = Notification.objects.filter(pk=notification_id, recipient=request.user).first()
    if not item:
        return Response({"detail": "Notificación no encontrada."}, status=404)
    if not item.read_at:
        item.read_at = timezone.now()
        item.save(update_fields=("read_at",))
    return Response(_notification_payload(item))
