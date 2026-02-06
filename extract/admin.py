from django.contrib import admin

from .models import ExtractionJob


@admin.register(ExtractionJob)
class ExtractionJobAdmin(admin.ModelAdmin):
    list_display = ("id", "status", "current_step", "total_steps", "started_at", "finished_at")
    list_filter = ("status",)
    ordering = ("-created_at",)
    search_fields = ("id",)
