from django.contrib import admin

from .models import Capability, CapabilityExecution, CapabilityType, Correspondant


@admin.register(Correspondant)
class CorrespondantAdmin(admin.ModelAdmin):
    list_display = ("name", "base_url", "enabled")
    prepopulated_fields = {"display_name": ("name",)}


@admin.register(CapabilityType)
class CapabilityTypeAdmin(admin.ModelAdmin):
    list_display = ("slug", "description")
    readonly_fields = ("slug", "description", "input_schema", "output_schema", "config_schema")

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Capability)
class CapabilityAdmin(admin.ModelAdmin):
    list_display = ("name", "correspondant", "capability_type", "enabled", "priority")
    list_filter = ("correspondant", "capability_type", "enabled")
    search_fields = ("name", "correspondant__name")


@admin.register(CapabilityExecution)
class CapabilityExecutionAdmin(admin.ModelAdmin):
    list_display = ("capability", "status", "duration_ms", "created_at")
    list_filter = ("status",)
    readonly_fields = ("capability", "input", "output", "error", "status", "duration_ms", "created_at")

    def has_add_permission(self, request):
        return False
