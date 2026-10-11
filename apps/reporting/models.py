import uuid

from django.conf import settings
from django.db import models


class Notification(models.Model):
    """Private, in-app message. Content is intentionally metadata-only."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    event_id = models.UUIDField()
    kind = models.CharField(max_length=32)
    title = models.CharField(max_length=120)
    message = models.CharField(max_length=240)
    target_path = models.CharField(max_length=180)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [models.UniqueConstraint(fields=("recipient", "event_id"), name="uniq_notification_recipient_event")]
        indexes = [models.Index(fields=("recipient", "read_at", "created_at"), name="notification_inbox_idx")]

    def save(self, *args, **kwargs):
        # Notifications only link to same-origin screens; never allow open redirects.
        if not self.target_path.startswith("/trayectoria/") or self.target_path.startswith("//"):
            raise ValueError("La notificación requiere una ruta interna de trayectoria.")
        return super().save(*args, **kwargs)
