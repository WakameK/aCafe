from django.urls import path

from . import views

urlpatterns = [
    path("users/<int:user_id>/information-sheet/", views.generate_information_sheet, name="sosuke-info-sheet"),
]
