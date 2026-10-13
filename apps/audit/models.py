import uuid

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db import models


class AuditEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="audit_events")
    action = models.CharField(max_length=80)
    object_type = models.CharField(max_length=80)
    object_id = models.CharField(max_length=80)
    scope_type = models.CharField(max_length=24, blank=True)
    scope_id = models.CharField(max_length=80, blank=True)
    reason = models.CharField(max_length=300, blank=True)
    result = models.CharField(max_length=16, default="success")
    correlation_id = models.UUIDField(default=uuid.uuid4, db_index=True)
    safe_metadata = models.JSONField(default=dict, blank=True)
    occurred_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ("-occurred_at",)
        verbose_name = "evento de auditoría"
        verbose_name_plural = "eventos de auditoría"

    def save(self, *args, **kwargs):
        if self.pk and type(self).objects.filter(pk=self.pk).exists():
            raise PermissionDenied("Los eventos de auditoría son inmutables.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionDenied("Los eventos de auditoría no se pueden eliminar.")
