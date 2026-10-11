from django.urls import path

from . import api

app_name = "support"
urlpatterns = [
    path("api/v1/support/", api.api_support, name="api-support"),
    path("api/v1/support/scan/", api.api_scan, name="api-support-scan"),
    path("api/v1/support/cases/", api.api_create_case, name="api-support-create-case"),
    path("api/v1/support/cases/<uuid:case_id>/actions/", api.api_case_action, name="api-support-case-action"),
    path("api/v1/support/cases/<uuid:case_id>/close/", api.api_close_case, name="api-support-close-case"),
    path("api/v1/support/cases/<uuid:case_id>/discard/", api.api_discard_case, name="api-support-discard-case"),
]
