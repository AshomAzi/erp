from . import views
from django.urls import path

urlpatterns = [
    path('', views.home, name='home'), 
    path('forgot-password/', views.forgot_password, name='forgot_password'),
]