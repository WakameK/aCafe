from django.contrib import admin

from .models import SpaceRoom


@admin.register(SpaceRoom)
class SpaceRoomAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "heat", "is_permanent", "created_at")
    list_editable = ("is_permanent",)