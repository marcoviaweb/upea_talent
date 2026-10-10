from django.db import DatabaseError, connection
from django.http import JsonResponse


def live(request):
    """Confirm that the Django process can answer requests."""
    return JsonResponse({"status": "ok", "service": "upea-talent"})


def ready(request):
    """Confirm that the app can reach its configured PostgreSQL database."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except DatabaseError:
        return JsonResponse({"status": "unavailable", "database": "disconnected"}, status=503)
    return JsonResponse({"status": "ok", "database": "connected"})
