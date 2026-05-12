from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('index/', views.index, name='index'),
    path('profile/',views.profile, name='profile'),
    path('chat/', views.chat_page, name='chat'),
    path('chat_api/', views.chat_api, name='chat_api'),
    path('register/', views.register, name='register'),
    path('login/', views.login, name='login'),
    path('export-chat-log/', views.export_chat_log, name='export_chat_log'),
    path('update_name/', views.update_name, name='update_name'),
]
