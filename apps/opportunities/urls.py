from django.urls import path

from . import api

app_name = "opportunities"

urlpatterns = [
    path("api/v1/opportunities/", api.api_opportunities, name="list"),
    path("api/v1/opportunities/create/", api.api_create_opportunity, name="create"),
    path("api/v1/opportunities/<uuid:opportunity_id>/close/", api.api_close_opportunity, name="close"),
    path("api/v1/opportunities/<uuid:opportunity_id>/versions/", api.api_new_version, name="new-version"),
    path("api/v1/opportunity-versions/<uuid:version_id>/publish/", api.api_publish, name="publish"),
    path("api/v1/opportunity-versions/<uuid:version_id>/eligibility/", api.api_check_eligibility, name="eligibility"),
    path("api/v1/opportunity-versions/<uuid:version_id>/apply/", api.api_apply, name="apply"),
    path("api/v1/applications/<uuid:application_id>/withdraw/", api.api_withdraw, name="withdraw"),
    path("api/v1/applications/<uuid:application_id>/decision/", api.api_decide, name="decision"),
]
