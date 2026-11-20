from django.urls import path
from . import views

urlpatterns = [
    path("", views.supervisor, name="supervisor"),
    path("tasks/create/", views.create_task, name="create_task"),
    path("submissions/<int:submission_id>/<str:decision>/", views.review_submission, name="review_submission"),
]