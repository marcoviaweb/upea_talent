from django.db import transaction

from .models import Notification


def notify_after_commit(*, event_id, recipient_ids, kind, title, message, target_path):
    """Create deduplicated notifications only after the enclosing transaction commits."""
    ids = tuple({str(pk) for pk in recipient_ids if pk})
    if not ids:
        return

    def create_notifications():
        Notification.objects.bulk_create([
            Notification(recipient_id=user_id, event_id=event_id, kind=kind, title=title,
                         message=message, target_path=target_path)
            for user_id in ids
        ], ignore_conflicts=True)

    transaction.on_commit(create_notifications, robust=True)
