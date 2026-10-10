from django.urls import path

from . import api, views

app_name = "profiles"

urlpatterns = [
    path("api/v1/csrf/", api.csrf_token, name="api-csrf"),
    path("api/v1/auth/login/", api.api_login, name="api-login"),
    path("api/v1/auth/logout/", api.api_logout, name="api-logout"),
    path("api/v1/home/", api.api_home, name="api-home"),
    path("api/v1/groups/<uuid:offering_id>/", api.api_group_roster, name="api-group-roster"),
    path("api/v1/enrollments/<uuid:enrollment_id>/", api.api_enrollment_profile, name="api-enrollment-profile"),
    path("api/v1/enrollments/<uuid:enrollment_id>/records/<str:record_type>/", api.api_create_development, name="api-development-create"),
    path("api/v1/enrollments/<uuid:enrollment_id>/records/<str:record_type>/<uuid:record_id>/", api.api_update_development, name="api-development-update"),
    path("api/v1/records/<str:record_type>/<uuid:record_id>/review/", api.api_review_development, name="api-development-review"),
    path("acceso/", views.frontend_app, name="login"),
    path("salir/", views.frontend_app, name="logout"),
    path("trayectoria/", views.frontend_app, name="trajectory-home"),
    path("trayectoria/evidencias/", views.frontend_app, name="evidence-home"),
    path("trayectoria/puntos/", views.frontend_app, name="points-home"),
    path("trayectoria/oportunidades/", views.frontend_app, name="opportunities-home"),
    path("trayectoria/evaluaciones/", views.frontend_app, name="evaluations-home"),
    path("trayectoria/grupo/<uuid:offering_id>/", views.frontend_app, name="group-roster"),
    path("trayectoria/matricula/<uuid:enrollment_id>/", views.frontend_app, name="enrollment-profile"),
    path("trayectoria/matricula/<uuid:enrollment_id>/nuevo/<str:record_type>/", views.frontend_app, name="development-create"),
    path("trayectoria/matricula/<uuid:enrollment_id>/editar/<str:record_type>/<uuid:record_id>/", views.frontend_app, name="development-edit"),
    path("trayectoria/revisar/<str:record_type>/<uuid:record_id>/", views.frontend_app, name="development-review"),
]
