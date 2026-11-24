from django.urls import path

from . import views

urlpatterns = [
    path("rooms/", views.rooms, name="space-rooms"),
    path("rooms/<slug:slug>/", views.room_detail, name="space-room-detail"),
]
