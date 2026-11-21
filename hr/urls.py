from django.urls import path
from . import views

urlpatterns = [
    path("", views.hr, name="hr"),
    path("assign-mentor/", views.assign_mentor, name="assign_mentor"),
    path("leaves/<int:leave_id>/<str:decision>/", views.review_leave, name="review_leave"),
    path("reports/export/", views.export_reports, name="export_hr_reports"),
]