from django.urls import path
from . import views

urlpatterns = [
    path("", views.room_view, name="desk_room"),
    path("send/", views.send_message, name="desk_send"),
    path("messages/", views.get_messages, name="desk_messages"),
    path("create_room/", views.create_room, name="create_room"),
]
