from django.urls import path

from . import views

urlpatterns = [
    path("fires/", views.fires, name="desk-fires"),
    path("fires/<int:fire_id>/", views.fire_detail, name="desk-fire-detail"),
    path("fires/<int:fire_id>/join/", views.join, name="desk-fire-join"),
    path("fires/<int:fire_id>/messages/", views.messages, name="desk-fire-messages"),
    path("fires/<int:fire_id>/gifts/", views.gifts, name="desk-fire-gifts"),
]
