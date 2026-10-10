from django.contrib import admin

from .models import AcademicPeriod, Career, Course, CourseOffering, Institution


class TechnicalAdminOnly(admin.ModelAdmin):
    """Catalog setup is restricted to technical superusers until scoped UI exists."""
    def has_module_permission(self, request):
        return request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_add_permission(self, request):
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return False


for model in (Institution, Career, AcademicPeriod, Course, CourseOffering):
    admin.site.register(model, TechnicalAdminOnly)
