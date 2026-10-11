from collections import Counter
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.accounts.models import RoleAssignment
from apps.accounts.permissions import current_role_assignments
from apps.academics.models import CourseEnrollment, CourseOffering, Enrollment, TeachingAssignment
from apps.activities.services import can_manage_spd
from apps.audit.services import record_event
from .models import EvaluationAggregate, EvaluationCampaign, EvaluationEligibility, EvaluationSubmission, EvaluationTarget


QUESTIONNAIRE_VERSION = "UPEA-STRUCTURED-1"
MINIMUM_PRIVACY_THRESHOLD = 5
QUESTIONS = (
    ("clarity", "Explica los contenidos de forma clara."),
    ("organization", "Organiza las actividades y los materiales del curso."),
    ("coverage", "Desarrolla los contenidos previstos para la asignatura."),
    ("feedback", "Brinda retroalimentación útil y oportuna."),
    ("punctuality", "Cumple los horarios y actividades programadas."),
    ("availability", "Atiende consultas académicas con respeto."),
    ("equity", "Promueve un trato respetuoso e igualitario."),
)
SCALE_LABELS = {1: "Nunca", 2: "Pocas veces", 3: "A veces", 4: "Casi siempre", 5: "Siempre"}


def manageable_careers(user):
    from apps.academics.models import Career
    if user.is_superuser:
        return set(Career.objects.values_list("pk", flat=True))
    roles = current_role_assignments(user)
    career_ids = set(roles.filter(
        role__in=(RoleAssignment.Role.CAREER_ADMIN, RoleAssignment.Role.COORDINATOR),
        scope=RoleAssignment.Scope.CAREER,
    ).values_list("career_id", flat=True))
    institution_ids = roles.filter(
        role=RoleAssignment.Role.INSTITUTION_ADMIN, scope=RoleAssignment.Scope.INSTITUTION,
    ).values_list("institution_id", flat=True)
    career_ids.update(Career.objects.filter(institution_id__in=institution_ids).values_list("pk", flat=True))
    return career_ids


def _authorized_manager(user, career):
    if not can_manage_spd(user, career):
        raise PermissionDenied("Solo coordinación o administración autorizada puede gestionar campañas de esta carrera.")


def _valid_assignments(offering, on_date=None):
    on_date = on_date or timezone.localdate()
    assignments = TeachingAssignment.objects.filter(
        offering=offering, active=True, starts_on__lte=on_date,
    ).filter(models_end_date(on_date)).select_related("user")
    return [assignment for assignment in assignments if assignment.user.role_assignments.filter(
        role=assignment.role, scope=RoleAssignment.Scope.GROUP, group=offering,
        active=True, starts_at__lte=on_date,
    ).filter(Q(ends_at__isnull=True) | Q(ends_at__gte=on_date)).exists()]


def models_end_date(on_date):
    from django.db.models import Q
    return Q(ends_on__isnull=True) | Q(ends_on__gte=on_date)


@transaction.atomic
def create_campaign(*, actor, offering_id, title, opens_at, closes_at, minimum_responses=5):
    offering = CourseOffering.objects.select_for_update().select_related("course__career", "period").get(pk=offering_id)
    career = offering.course.career
    _authorized_manager(actor, career)
    title = str(title or "").strip()
    if not title or len(title) > 180:
        raise ValidationError("Indica un título de campaña de hasta 180 caracteres.")
    minimum_responses = int(minimum_responses)
    if minimum_responses < MINIMUM_PRIVACY_THRESHOLD or minimum_responses > 100:
        raise ValidationError("El mínimo configurable debe estar entre 5 y 100 respuestas.")
    if closes_at <= opens_at:
        raise ValidationError("El cierre debe ser posterior a la apertura.")
    if closes_at <= timezone.now():
        raise ValidationError("La fecha de cierre debe estar en el futuro.")
    if not _valid_assignments(offering):
        raise ValidationError("El grupo no tiene una asignación docente o auxiliar vigente para evaluar.")

    previous = EvaluationCampaign.objects.select_for_update().filter(offering=offering).order_by("-version").first()
    if previous:
        if previous.status in {EvaluationCampaign.Status.OPEN, EvaluationCampaign.Status.CLOSED, EvaluationCampaign.Status.PUBLISHED}:
            raise ValidationError("Este grupo ya tuvo una campaña abierta en el periodo. Para proteger la participación, no se permite iniciar una encuesta solapada.")
        old_status = previous.status
        if previous.status != EvaluationCampaign.Status.CANCELLED:
            previous.status = EvaluationCampaign.Status.CANCELLED
            previous.save(update_fields=("status",))
            record_event(actor=actor, action="evaluation.campaign_superseded", obj=previous,
                         scope_type="career", scope_id=career.pk,
                         reason="Versión reemplazada antes de recibir respuestas.",
                         safe_metadata={"previousStatus": old_status})
        version = previous.version + 1
    else:
        version = 1
    campaign = EvaluationCampaign.objects.create(
        career=career, period=offering.period, offering=offering, title=title,
        version=version, questionnaire_version=QUESTIONNAIRE_VERSION,
        minimum_responses=minimum_responses, opens_at=opens_at, closes_at=closes_at,
        created_by=actor, supersedes=previous,
    )
    record_event(actor=actor, action="evaluation.campaign_created", obj=campaign,
                 scope_type="career", scope_id=career.pk,
                 reason="Creación de campaña de evaluación estructurada.",
                 safe_metadata={"version": version, "offering": str(offering.pk), "questionnaire": QUESTIONNAIRE_VERSION})
    return campaign


@transaction.atomic
def publish_campaign(*, actor, campaign_id):
    campaign = EvaluationCampaign.objects.select_for_update().select_related("offering__course", "career").get(pk=campaign_id)
    _authorized_manager(actor, campaign.career)
    if campaign.status != EvaluationCampaign.Status.DRAFT:
        raise ValidationError("Solo se puede abrir una campaña en borrador.")
    if campaign.closes_at <= timezone.now():
        raise ValidationError("La campaña ya pasó su fecha de cierre.")
    assignments = list(_valid_assignments(campaign.offering))
    if not assignments:
        raise ValidationError("No hay asignaciones docentes o auxiliares vigentes en el grupo.")
    roster = CourseEnrollment.objects.filter(
        offering=campaign.offering, active=True, enrollment__status=Enrollment.Status.ACTIVE,
        enrollment__career=campaign.career, enrollment__period=campaign.period,
    ).select_related("enrollment__student__user")
    for assignment in assignments:
        eligible_roster = [row for row in roster if row.enrollment.student.user_id != assignment.user_id]
        if len(eligible_roster) < campaign.minimum_responses:
            raise ValidationError(
                f"El grupo tiene {len(eligible_roster)} estudiantes habilitables para una de las asignaciones; "
                f"el mínimo de privacidad es {campaign.minimum_responses}."
            )
        subject_name = assignment.user.get_full_name() or assignment.user.username
        target = EvaluationTarget.objects.create(
            campaign=campaign, assignment=assignment, subject=assignment.user,
            subject_role=assignment.role, subject_name=subject_name,
        )
        EvaluationEligibility.objects.bulk_create([
            EvaluationEligibility(campaign=campaign, target=target, enrollment=row.enrollment)
            for row in eligible_roster
        ])
    campaign.status = EvaluationCampaign.Status.OPEN
    campaign.published_at = timezone.now()
    campaign.save(update_fields=("status", "published_at"))
    record_event(actor=actor, action="evaluation.campaign_opened", obj=campaign,
                 scope_type="career", scope_id=campaign.career_id,
                 reason="Campaña publicada con el padrón del grupo congelado.",
                 safe_metadata={"version": campaign.version, "targetCount": len(assignments), "questionnaire": campaign.questionnaire_version})
    return campaign


@transaction.atomic
def close_campaign(*, actor, campaign_id, reason="Cierre de campaña"):
    campaign = EvaluationCampaign.objects.select_for_update().select_related("career").get(pk=campaign_id)
    _authorized_manager(actor, campaign.career)
    if campaign.status != EvaluationCampaign.Status.OPEN:
        raise ValidationError("Solo se puede cerrar una campaña abierta.")
    campaign.status = EvaluationCampaign.Status.CLOSED
    campaign.closed_at = timezone.now()
    campaign.save(update_fields=("status", "closed_at"))
    record_event(actor=actor, action="evaluation.campaign_closed", obj=campaign,
                 scope_type="career", scope_id=campaign.career_id,
                 reason=str(reason).strip()[:300] or "Cierre de campaña",
                 safe_metadata={"version": campaign.version})
    return campaign


def _aggregate_target(campaign, target, now):
    ballots = list(EvaluationSubmission.objects.filter(campaign=campaign, target=target).values_list("response", flat=True))
    count = len(ballots)
    state = EvaluationAggregate.State.PUBLISHED if count >= campaign.minimum_responses else EvaluationAggregate.State.SUPPRESSED
    metrics = {}
    if state == EvaluationAggregate.State.PUBLISHED:
        for code, _label in QUESTIONS:
            values = [ballot[code] for ballot in ballots]
            distribution = Counter(values)
            metrics[code] = {
                "mean": round(sum(values) / count, 2),
                "distribution": {str(score): distribution.get(score, 0) for score in range(1, 6)},
            }
    return EvaluationAggregate.objects.create(
        campaign=campaign, target=target, response_count=count,
        metrics=metrics, state=state, published_at=now,
    )


@transaction.atomic
def publish_results(*, actor, campaign_id):
    campaign = EvaluationCampaign.objects.select_for_update().select_related("career").get(pk=campaign_id)
    _authorized_manager(actor, campaign.career)
    if campaign.status != EvaluationCampaign.Status.CLOSED:
        raise ValidationError("Cierra la campaña antes de publicar sus resultados agregados.")
    now = timezone.now()
    aggregates = [_aggregate_target(campaign, target, now) for target in campaign.targets.all()]
    campaign.status = EvaluationCampaign.Status.PUBLISHED
    campaign.results_published_at = now
    campaign.save(update_fields=("status", "results_published_at"))
    published_count = sum(row.state == EvaluationAggregate.State.PUBLISHED for row in aggregates)
    record_event(actor=actor, action="evaluation.results_published", obj=campaign,
                 scope_type="career", scope_id=campaign.career_id,
                 reason="Publicación de agregados que superan el umbral configurado.",
                 safe_metadata={"version": campaign.version, "publishedTargets": published_count, "suppressedTargets": len(aggregates) - published_count})
    return campaign, aggregates


@transaction.atomic
def cancel_campaign(*, actor, campaign_id, reason):
    campaign = EvaluationCampaign.objects.select_for_update().select_related("career").get(pk=campaign_id)
    _authorized_manager(actor, campaign.career)
    reason = str(reason or "").strip()
    if len(reason) < 10:
        raise ValidationError("Explica la cancelación en al menos diez caracteres.")
    if campaign.status != EvaluationCampaign.Status.DRAFT:
        raise ValidationError("Una campaña abierta no se puede cancelar porque revelarías si ya recibió respuestas. Puedes cerrarla y publicar su agregado protegido.")
    campaign.status = EvaluationCampaign.Status.CANCELLED
    campaign.save(update_fields=("status",))
    record_event(actor=actor, action="evaluation.campaign_cancelled", obj=campaign,
                 scope_type="career", scope_id=campaign.career_id, reason=reason,
                 safe_metadata={"version": campaign.version})
    return campaign


@transaction.atomic
def submit_ballot(*, actor, target_id, response):
    try:
        eligibility = EvaluationEligibility.objects.select_for_update().select_related(
            "campaign__offering__course", "target__subject",
        ).get(target_id=target_id, enrollment__student__user=actor)
    except EvaluationEligibility.DoesNotExist:
        raise PermissionDenied("No tienes habilitación para responder esta evaluación.")
    campaign = EvaluationCampaign.objects.select_for_update().get(pk=eligibility.campaign_id)
    if campaign.status != EvaluationCampaign.Status.OPEN:
        raise ValidationError("La campaña no está abierta para respuestas.")
    now = timezone.now()
    if now < campaign.opens_at or now >= campaign.closes_at:
        raise ValidationError("La campaña está fuera de su periodo de respuesta.")
    if eligibility.enrollment.status != Enrollment.Status.ACTIVE or not CourseEnrollment.objects.filter(
        enrollment=eligibility.enrollment, offering=campaign.offering, active=True,
    ).exists():
        raise PermissionDenied("La matrícula ya no está habilitada para esta evaluación.")
    if not current_role_assignments(actor).filter(
        role=RoleAssignment.Role.STUDENT, scope=RoleAssignment.Scope.CAREER,
        career=campaign.career,
    ).exists():
        raise PermissionDenied("Tu rol estudiantil ya no está vigente para esta carrera.")
    if eligibility.answered:
        raise ValidationError("Ya registraste tu respuesta para esta persona y asignación.")
    if not isinstance(response, dict) or set(response) != {code for code, _label in QUESTIONS}:
        raise ValidationError("Responde todos los criterios estructurados de la encuesta.")
    values = {}
    for code, _label in QUESTIONS:
        value = response.get(code)
        if isinstance(value, bool) or not isinstance(value, int) or value not in SCALE_LABELS:
            raise ValidationError("Cada criterio debe usar una opción válida de la escala de 1 a 5.")
        values[code] = value
    EvaluationSubmission.objects.create(campaign=campaign, target=eligibility.target, response=values)
    eligibility.answered = True
    eligibility.save(update_fields=("answered",))
    # Deliberately no voter-identifying audit event: a response audit actor/time could defeat anonymity.
    return eligibility

