from django.urls import path

from . import api

app_name = "reporting"
urlpatterns = [
    path("api/v1/reports/", api.api_report, name="api-report"),
    path("api/v1/audit/", api.api_audit, name="api-audit"),
    path("api/v1/academic-admin/", api.api_academic_admin, name="api-academic-admin"),
    path("api/v1/notifications/", api.api_notifications, name="api-notifications"),
    path("api/v1/notifications/<uuid:notification_id>/read/", api.api_mark_notification_read, name="api-notification-read"),
]
