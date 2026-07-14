from django.urls import path
from . import views

urlpatterns = [
    path('', views.atelier, name='atelier'),
]
