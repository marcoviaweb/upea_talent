from django.contrib import admin

from .models import TransferAdjustment, TransferAllocation, TransferMovement, TransferRequest, TransferReview, TransferRiskAlert


class TransferAllocationInline(admin.TabularInline):
    model = TransferAllocation
    extra = 0
    readonly_fields = ("source_movement", "amount")
    can_delete = False


class TransferReviewInline(admin.TabularInline):
    model = TransferReview
    extra = 0
    readonly_fields = ("reviewer", "decision", "reason", "decided_at")
    can_delete = False


@admin.register(TransferRequest)
class TransferRequestAdmin(admin.ModelAdmin):
    list_display = ("submitted_at", "sender", "recipient", "activity", "amount", "status")
    list_filter = ("status", "sender__career")
    search_fields = ("sender__student__student_number", "recipient__student__student_number", "activity__title")
    readonly_fields = ("sender", "recipient", "activity", "amount", "reason", "idempotency_key", "risk_flags", "submitted_at", "resolved_by", "resolved_at")
    inlines = (TransferAllocationInline, TransferReviewInline)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(TransferRiskAlert)
class TransferRiskAlertAdmin(admin.ModelAdmin):
    list_display = ("created_at", "code", "request", "status", "resolved_by")
    list_filter = ("code", "status")
    readonly_fields = ("request", "code", "description", "created_at", "resolved_by", "resolution_reason", "resolved_at")

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(TransferMovement)
class TransferMovementAdmin(admin.ModelAdmin):
    list_display = ("created_at", "request", "enrollment", "side", "points", "source_movement")
    readonly_fields = tuple(field.name for field in TransferMovement._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(TransferAdjustment)
class TransferAdjustmentAdmin(admin.ModelAdmin):
    list_display = ("created_at", "alert", "original_movement", "enrollment", "points", "actor")
    readonly_fields = tuple(field.name for field in TransferAdjustment._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
