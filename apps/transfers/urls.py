from django.urls import path

from . import api

urlpatterns = [
    path("api/v1/transfers/", api.api_transfers, name="transfers-list"),
    path("api/v1/transfers/<uuid:request_id>/cancel/", api.api_cancel_transfer, name="transfers-cancel"),
    path("api/v1/transfers/<uuid:request_id>/review/", api.api_review_transfer, name="transfers-review"),
    path("api/v1/transfers/alerts/<uuid:alert_id>/resolve/", api.api_resolve_risk, name="transfers-alert-resolve"),
]
