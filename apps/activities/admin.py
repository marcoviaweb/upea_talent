from django.contrib import admin
from django.utils import timezone

from apps.audit.services import record_event
from .models import Activity, ActivityCategory, EvidenceFile, PointsMovement, Regulation, ReviewDecision


class CategoryInline(admin.TabularInline):
    model = ActivityCategory
    extra = 0


@admin.register(Regulation)
class RegulationAdmin(admin.ModelAdmin):
    list_display = ("career", "version", "title", "effective_from", "published")
    list_filter = ("career", "published")
    inlines = (CategoryInline,)
    readonly_fields = ("created_at", "published_at")

    def save_model(self, request, obj, form, change):
        was_published = obj.pk and Regulation.objects.filter(pk=obj.pk, published=True).exists()
        if not change:
            obj.created_by = request.user
        if obj.published and not obj.published_at:
            obj.published_by = request.user
            obj.published_at = timezone.now()
        super().save_model(request, obj, form, change)
        if obj.published and not was_published:
            record_event(actor=request.user, action="spd.regulation_published", obj=obj, scope_type="career", scope_id=obj.career_id, reason="Publicación administrativa de reglamento SPD", safe_metadata={"version": obj.version})


class EvidenceInline(admin.TabularInline):
    model = EvidenceFile
    extra = 0
    readonly_fields = ("file", "original_name", "content_type", "size", "version", "uploaded_by", "uploaded_at")
    can_delete = False


class ReviewInline(admin.TabularInline):
    model = ReviewDecision
    extra = 0
    readonly_fields = ("reviewer", "outcome", "note", "created_at")
    can_delete = False


@admin.register(Activity)
class ActivityAdmin(admin.ModelAdmin):
    list_display = ("title", "enrollment", "category", "status", "created_at", "reviewed_by")
    list_filter = ("status", "category__regulation__career")
    search_fields = ("title", "enrollment__student__student_number")
    readonly_fields = ("created_at", "updated_at", "reviewed_at")
    inlines = (EvidenceInline, ReviewInline)


@admin.register(PointsMovement)
class PointsMovementAdmin(admin.ModelAdmin):
    list_display = ("enrollment", "points", "category", "actor", "created_at", "reversal_of")
    readonly_fields = tuple(field.name for field in PointsMovement._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
