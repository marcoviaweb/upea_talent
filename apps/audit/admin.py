from django.contrib import admin

from .models import AuditEvent


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    list_display = ("occurred_at", "actor", "action", "object_type", "object_id", "scope_type", "result")
    list_filter = ("action", "scope_type", "result")
    search_fields = ("object_type", "object_id", "actor__username")
    readonly_fields = tuple(field.name for field in AuditEvent._meta.fields)

    def has_module_permission(self, request):
        return request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
