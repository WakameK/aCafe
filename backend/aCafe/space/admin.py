from django.contrib import admin

from .models import SpaceRoom


@admin.register(SpaceRoom)
class SpaceRoomAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "created_at")
    search_fields = ("name", "slug")
