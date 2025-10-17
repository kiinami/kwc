from django.contrib import admin

from .models import ImageDecision


@admin.register(ImageDecision)
class ImageDecisionAdmin(admin.ModelAdmin):
	list_display = ("folder", "filename", "decision", "decided_at")
	list_filter = ("decision",)
	search_fields = ("folder", "filename")
