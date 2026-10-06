from django.urls import path

from . import views

urlpatterns = [
    path("seats/", views.seats, name="desk-seats"),
    path("seats/<int:seat_id>/sit/", views.sit_seat, name="desk-seat-sit"),
    path("rooms/", views.rooms, name="desk-rooms"),
    path("rooms/<int:room_id>/atmosphere/", views.regenerate_atmosphere, name="desk-room-atmosphere"),
    path("rooms/<int:room_id>/gifts/", views.send_gift, name="desk-room-gift"),
]
