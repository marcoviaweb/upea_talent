from django.contrib import admin

from .models import Application, ApplicationDecision, EligibilitySnapshot, Opportunity, OpportunityRequirement, OpportunityVersion


class RequirementInline(admin.TabularInline):
    model = OpportunityRequirement
    extra = 0


@admin.register(Opportunity)
class OpportunityAdmin(admin.ModelAdmin):
    list_display = ("id", "owner", "status", "created_at")
    list_filter = ("status",)
    readonly_fields = ("created_at", "updated_at")


@admin.register(OpportunityVersion)
class OpportunityVersionAdmin(admin.ModelAdmin):
    list_display = ("title", "opportunity", "version_number", "capacity", "opens_at", "closes_at", "published_at")
    list_filter = ("kind", "published_at")
    filter_horizontal = ("careers",)
    inlines = (RequirementInline,)
    readonly_fields = ("published_at", "published_by", "created_at")

    def has_change_permission(self, request, obj=None):
        if obj and obj.published_at:
            return False
        return super().has_change_permission(request, obj)


@admin.register(Application)
class ApplicationAdmin(admin.ModelAdmin):
    list_display = ("id", "version", "enrollment", "status", "submitted_at")
    list_filter = ("status",)
    readonly_fields = tuple(f.name for f in Application._meta.fields)


@admin.register(EligibilitySnapshot)
class EligibilitySnapshotAdmin(admin.ModelAdmin):
    list_display = ("id", "version", "enrollment", "overall_status", "computed_at")
    readonly_fields = tuple(f.name for f in EligibilitySnapshot._meta.fields)


@admin.register(ApplicationDecision)
class ApplicationDecisionAdmin(admin.ModelAdmin):
    list_display = ("application", "decision", "actor", "decided_at")
    readonly_fields = tuple(f.name for f in ApplicationDecision._meta.fields)
