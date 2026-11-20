from django.urls import path
from . import views

urlpatterns = [
    path("", views.employee, name="employee"),
    path("attendance/record/", views.record_attendance, name="record_attendance"),
    path("leaves/request/", views.request_leave, name="request_leave"),
    path("tasks/<int:task_id>/submit/", views.submit_task, name="submit_task"),
]