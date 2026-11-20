from django.urls import path
from . import views

urlpatterns = [
    path("", views.admin_dashboard, name="admin_dashboard"),
    path("users/create/", views.create_user, name="create_user"),
    path("users/update-role/", views.update_user_role, name="update_user_role"),
    path("departments/create/", views.create_department, name="create_department"),
    path("departments/update/", views.update_department, name="update_department"),
    path("settings/", views.save_organization_settings, name="save_organization_settings"),
]