from django.urls import path

from . import views

urlpatterns = [
    path("chat/", views.chat, name="sosuke-chat"),
    path("users/<int:user_id>/information-sheet/", views.generate_information_sheet, name="sosuke-info-sheet"),
]
