from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("apps.profiles.urls")),
    path("", include("apps.activities.urls")),
    path("", include("apps.opportunities.urls")),
    path("", include("apps.transfers.urls")),
    path("", include("apps.evaluations.urls")),
    path("", include("apps.support.urls")),
    path("", include("apps.reporting.urls")),
    path("", include("apps.core.urls")),
]
