from django.urls import path
from . import views

urlpatterns = [
    path("", views.access_denied, name="access_denied")
]