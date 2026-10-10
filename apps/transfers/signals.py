from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.activities.models import PointsMovement
from .models import TransferAllocation, TransferRequest, TransferRiskAlert


@receiver(post_save, sender=PointsMovement)
def flag_transfer_after_origin_reversal(sender, instance, created, **kwargs):
    if not created or not instance.reversal_of_id:
        return
    affected = TransferAllocation.objects.filter(
        source_movement_id=instance.reversal_of_id,
        request__status=TransferRequest.Status.APPROVED,
    ).select_related("request__sender__career")
    for allocation in affected:
        TransferRiskAlert.objects.get_or_create(
            request=allocation.request, code="origin_revoked_after_transfer",
            defaults={"description": "El mérito SPD de origen fue revocado después de una transferencia aprobada. Revisar y regularizar."},
        )
