from django.urls import path

from . import api

urlpatterns = [
    path("api/v1/evidence/", api.api_evidence, name="api-evidence"),
    path("api/v1/evidence/candidates/", api.api_evidence_candidates, name="api-evidence-candidates"),
    path("api/v1/evidence/verified/", api.api_record_verified, name="api-evidence-verified"),
    path("api/v1/evidence/<uuid:activity_id>/review/", api.api_review, name="api-evidence-review"),
    path("api/v1/evidence/<uuid:activity_id>/resubmit/", api.api_resubmit, name="api-evidence-resubmit"),
    path("api/v1/evidence/<uuid:activity_id>/revoke/", api.api_revoke, name="api-evidence-revoke"),
    path("api/v1/evidence/files/<uuid:file_id>/", api.api_evidence_file, name="api-evidence-file"),
    path("api/v1/spd/", api.api_spd, name="api-spd"),
]
