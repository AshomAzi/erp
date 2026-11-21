from django.urls import path

from . import views


urlpatterns = [
    path("", views.home, name="home"),
    path("logout/", views.logout_view, name="logout"),
    path("forgot-password/", views.forgot_password, name="forgot_password"),
    path("notifications/read/", views.mark_notifications_read, name="mark_notifications_read"),
]