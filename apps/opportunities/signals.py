from django.core.exceptions import ValidationError
from django.db.models.signals import m2m_changed
from django.dispatch import receiver

from .models import OpportunityVersion


@receiver(m2m_changed, sender=OpportunityVersion.careers.through)
def keep_published_version_careers_immutable(sender, instance, action, **kwargs):
    if action in {"pre_add", "pre_remove", "pre_clear"} and instance.published_at:
        raise ValidationError("Las carreras habilitadas de una versión publicada son inmutables; crea otra versión.")
