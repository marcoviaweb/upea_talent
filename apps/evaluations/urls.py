from django.urls import path

from . import api

app_name = "evaluations"

urlpatterns = [
    path("api/v1/evaluations/", api.api_evaluations, name="api-evaluations"),
    path("api/v1/evaluations/respond/", api.api_respond, name="api-evaluation-respond"),
    path("api/v1/evaluations/campaigns/<uuid:campaign_id>/open/", api.api_open_campaign, name="api-evaluation-open"),
    path("api/v1/evaluations/campaigns/<uuid:campaign_id>/close/", api.api_close_campaign, name="api-evaluation-close"),
    path("api/v1/evaluations/campaigns/<uuid:campaign_id>/publish-results/", api.api_publish_results, name="api-evaluation-publish-results"),
    path("api/v1/evaluations/campaigns/<uuid:campaign_id>/cancel/", api.api_cancel_campaign, name="api-evaluation-cancel"),
]
