"""Translate selected committed audit events into minimal internal notices."""
from django.db.models.signals import post_save
from django.db.models import Q
from django.dispatch import receiver

from apps.audit.models import AuditEvent


@receiver(post_save, sender=AuditEvent, dispatch_uid="reporting.notify_from_audit_event")
def notification_for_audit_event(sender, instance, created, **kwargs):
    if not created:
        return
    event_id = instance.pk

    def resolve_and_notify():
        from apps.accounts.models import RoleAssignment
        from apps.academics.models import Enrollment
        from apps.opportunities.models import Application, ApplicationDecision, OpportunityVersion
        from apps.support.models import SupportAction, SupportCase
        from apps.transfers.models import TransferRequest
        from .models import Notification

        try:
            event = AuditEvent.objects.get(pk=event_id)
        except AuditEvent.DoesNotExist:
            return
        actor_id = event.actor_id
        recipients, kind, title, message, path = [], "activity", "Actualización académica", "Hay una actualización que requiere tu atención.", "/trayectoria/"
        action = event.action
        if action in {"evidence.submitted", "evidence.resubmitted"}:
            recipients = list(RoleAssignment.objects.filter(active=True).filter(
                Q(scope="career", career_id=event.scope_id,
                  role__in=(RoleAssignment.Role.COORDINATOR, RoleAssignment.Role.CAREER_ADMIN))
                | Q(scope="group", group__course__career_id=event.scope_id,
                    role__in=(RoleAssignment.Role.TEACHER, RoleAssignment.Role.AUXILIARY, RoleAssignment.Role.EVIDENCE_REVIEWER))
            ).values_list("user_id", flat=True))
            kind, title, message, path = "evidence", "Evidencia pendiente de revisión", "Se presentó una evidencia para revisión en tu ámbito.", "/trayectoria/evidencias/"
        elif action.startswith("evidence."):
            from apps.activities.models import Activity
            activity = Activity.objects.filter(pk=event.object_id).select_related("enrollment__student").first()
            recipients = [activity.enrollment.student.user_id] if activity else []
            kind, title, message, path = "evidence", "Tu evidencia fue revisada", "Consulta el resultado y las observaciones en tu trayectoria.", "/trayectoria/evidencias/"
        elif action == "opportunity.application_submitted":
            application = Application.objects.filter(pk=event.object_id).select_related("version__opportunity").first()
            recipients = [application.version.opportunity.owner_id] if application else []
            kind, title, message, path = "application", "Nueva postulación recibida", "Una persona estudiante envió una postulación.", "/trayectoria/oportunidades/"
        elif action in {"opportunity.application_decided", "opportunity.application_withdrawn"}:
            decision = ApplicationDecision.objects.filter(pk=event.object_id).select_related("application__enrollment__student").first() if action.endswith("decided") else None
            application = decision.application if decision else Application.objects.filter(pk=event.object_id).select_related("enrollment__student").first()
            recipients = [application.enrollment.student.user_id] if application else []
            kind, title, message, path = "application", "Actualización de postulación", "Consulta el estado actualizado de tu postulación.", "/trayectoria/oportunidades/"
        elif action == "opportunity.published":
            version = OpportunityVersion.objects.filter(pk=event.object_id).first()
            recipients = list(Enrollment.objects.filter(status="active", career__in=version.careers.all()).values_list("student__user_id", flat=True).distinct()) if version else []
            kind, title, message, path = "opportunity", "Nueva oportunidad disponible", "Hay una oportunidad publicada para tu carrera.", "/trayectoria/oportunidades/"
        elif action == "transfer.submitted":
            transfer = TransferRequest.objects.filter(pk=event.object_id).first()
            recipients = [transfer.recipient.student.user_id] if transfer else []
            if transfer:
                recipients += list(RoleAssignment.objects.filter(active=True, scope="career", career_id=transfer.sender.career_id,
                    role__in=(RoleAssignment.Role.COORDINATOR, RoleAssignment.Role.CAREER_ADMIN)).values_list("user_id", flat=True))
            kind, title, message, path = "transfer", "Nueva solicitud de transferencia", "Hay una solicitud de reconocimiento de colaboración pendiente.", "/trayectoria/transferencias/"
        elif action.startswith("transfer."):
            transfer = TransferRequest.objects.filter(pk=event.object_id).first()
            recipients = [transfer.sender.student.user_id, transfer.recipient.student.user_id] if transfer else []
            kind, title, message, path = "transfer", "Actualización de transferencia", "Consulta el estado y el motivo registrado.", "/trayectoria/transferencias/"
        elif action in {"support.case_opened", "support.action_recorded", "support.case_closed", "support.case_discarded"}:
            case = SupportCase.objects.filter(pk=event.object_id).select_related("alert__enrollment__student").first()
            action_row = None
            if not case:
                action_row = SupportAction.objects.filter(pk=event.object_id).select_related("case__alert__enrollment__student").first()
                case = action_row.case if action_row else None
            if action_row and action_row.kind == SupportAction.Kind.STUDENT_RESPONSE:
                recipients = [case.assigned_to_id] if case and case.assigned_to_id else []
                title, message = "Respuesta recibida en acompañamiento", "El estudiante respondió al equipo asignado."
            else:
                recipients = [case.alert.enrollment.student.user_id] if case else []
            kind, title, message, path = "support", "Actualización de acompañamiento", "Hay una actualización en tu espacio de acompañamiento.", "/trayectoria/acompanamiento/"
        recipients = [user_id for user_id in set(recipients) if str(user_id) != str(actor_id)]
        Notification.objects.bulk_create([
            Notification(recipient_id=user_id, event_id=event.pk, kind=kind, title=title, message=message, target_path=path)
            for user_id in recipients
        ], ignore_conflicts=True)
        receipts = {
            "evidence.submitted": ("evidence", "Evidencia enviada", "Tu evidencia quedó registrada para revisión.", "/trayectoria/evidencias/"),
            "evidence.resubmitted": ("evidence", "Evidencia reenviada", "La versión corregida quedó registrada para revisión.", "/trayectoria/evidencias/"),
            "opportunity.application_submitted": ("application", "Postulación enviada", "Tu postulación quedó registrada.", "/trayectoria/oportunidades/"),
            "transfer.submitted": ("transfer", "Solicitud enviada", "Tu solicitud de transferencia quedó registrada.", "/trayectoria/transferencias/"),
        }
        if action in receipts:
            receipt_kind, receipt_title, receipt_message, receipt_path = receipts[action]
            Notification.objects.get_or_create(recipient_id=actor_id, event_id=event.pk, defaults={
                "kind": receipt_kind, "title": receipt_title, "message": receipt_message, "target_path": receipt_path,
            })

    from django.db import transaction
    transaction.on_commit(resolve_and_notify, robust=True)
