from decimal import Decimal

from django.core.exceptions import PermissionDenied
from django.db import transaction

from apps.accounts.permissions import current_role_assignments
from apps.academics.models import AcademicPeriod, Enrollment, GradeRecord
from apps.activities.models import Activity
from apps.activities.services import can_manage_spd
from apps.audit.services import record_event
from .models import SupportAlert, SupportRuleVersion


def manageable_careers(user):
    if user.is_superuser:
        from apps.academics.models import Career
        return Career.objects.filter(active=True)
    roles = current_role_assignments(user)
    ids = set(roles.filter(role="coordinator", scope="career").values_list("career_id", flat=True))
    ids.update(roles.filter(role="career_admin", scope="career").values_list("career_id", flat=True))
    ids.update(roles.filter(role="institution_admin", scope="institution").values_list("institution__careers__id", flat=True))
    from apps.academics.models import Career
    return Career.objects.filter(pk__in=ids, active=True)


def _verified_average(enrollment):
    grades = list(GradeRecord.objects.filter(enrollment=enrollment, status=GradeRecord.Status.VERIFIED, supersedes__isnull=True).select_related("offering"))
    if not grades:
        return None
    # Normalize mixed scales to 100 before comparing periods.
    values = [Decimal(row.grade_value) * Decimal(100) / Decimal(row.scale_snapshot) for row in grades]
    return sum(values) / len(values), len(values)


def _comparable_pairs(career, minimum_courses):
    """Only consecutive closed periods with completed enrollments and sufficient verified grades qualify."""
    enrollments = Enrollment.objects.filter(career=career, status=Enrollment.Status.COMPLETED,
        period__status=AcademicPeriod.Status.CLOSED).select_related("student__user", "period").order_by("student_id", "period__starts_on")
    by_student = {}
    for enrollment in enrollments:
        average = _verified_average(enrollment)
        by_student.setdefault(enrollment.student_id, {})[enrollment.period_id] = (enrollment, average)
    closed_period_ids = list(AcademicPeriod.objects.filter(career=career, status=AcademicPeriod.Status.CLOSED).order_by("starts_on").values_list("id", flat=True))
    for rows in by_student.values():
        # Require enrollment in adjacent closed periods; never jump across an absent/incomplete period.
        for prior_period_id, current_period_id in zip(closed_period_ids, closed_period_ids[1:]):
            if prior_period_id not in rows or current_period_id not in rows:
                continue
            prior, prior_metric = rows[prior_period_id]
            current, current_metric = rows[current_period_id]
            if prior_metric is None or current_metric is None:
                continue
            if prior_metric[1] < minimum_courses or current_metric[1] < minimum_courses:
                continue
            yield prior, prior_metric, current, current_metric


@transaction.atomic
def evaluate_active_rules(*, actor, career=None):
    careers = manageable_careers(actor)
    if career:
        if not careers.filter(pk=career.pk).exists():
            raise PermissionDenied("No tienes autorización para analizar esta carrera.")
        careers = careers.filter(pk=career.pk)
    created = []
    for rule in SupportRuleVersion.objects.filter(career__in=careers, active=True).select_related("career", "valid_from"):
        if rule.indicator != SupportRuleVersion.Indicator.VERIFIED_AVERAGE_DECLINE:
            continue
        for prior, previous, current, latest in _comparable_pairs(rule.career, rule.minimum_verified_courses):
            if current.period.starts_on < rule.valid_from.starts_on:
                continue
            delta = latest[0] - previous[0]
            if delta > -rule.threshold_points:
                continue
            alert, was_created = SupportAlert.objects.get_or_create(
                rule=rule, enrollment=current, period=current.period,
                defaults={"evidence_snapshot": {
                    "indicator": rule.get_indicator_display(), "previousPeriod": prior.period.name,
                    "currentPeriod": current.period.name, "previousAverage": str(previous[0].quantize(Decimal('0.01'))),
                    "currentAverage": str(latest[0].quantize(Decimal('0.01'))), "deltaPoints": str(delta.quantize(Decimal('0.01'))),
                    "previousVerifiedCourses": previous[1], "currentVerifiedCourses": latest[1],
                    "ruleVersion": rule.version, "thresholdPoints": str(rule.threshold_points),
                    "source": "Notas oficiales verificadas; promedios normalizados a escala 100.",
                }},
            )
            if was_created:
                created.append(alert)
                record_event(actor=actor, action="support.alert_created", obj=alert, scope_type="career", scope_id=rule.career_id,
                    reason="Señal generada por regla y datos verificados de periodos cerrados",
                    safe_metadata={"ruleVersion": rule.version, "period": current.period.code})
    return created


def period_indicators(enrollment):
    grades = GradeRecord.objects.filter(enrollment=enrollment, status=GradeRecord.Status.VERIFIED, supersedes__isnull=True)
    count = grades.count()
    average = None
    if count:
        values = [Decimal(g.grade_value) * Decimal(100) / Decimal(g.scale_snapshot) for g in grades]
        average = str((sum(values) / len(values)).quantize(Decimal("0.01")))
    return {
        "period": enrollment.period.name, "periodCode": enrollment.period.code,
        "periodStatus": enrollment.period.status, "enrollmentStatus": enrollment.status,
        "verifiedGrades": count, "averageOutOf100": average,
        "approvedActivities": Activity.objects.filter(enrollment=enrollment, status=Activity.Status.APPROVED).count(),
        "comparable": enrollment.status == Enrollment.Status.COMPLETED and enrollment.period.status == AcademicPeriod.Status.CLOSED and count >= 2,
    }
