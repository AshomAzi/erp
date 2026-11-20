from django.db import models


class Task(models.Model):
    PRIORITY_CHOICES = [
        ("low", "Low"),
        ("medium", "Medium"),
        ("high", "High"),
    ]

    title = models.CharField(max_length=160)
    assigned_to = models.ForeignKey(
        "signup.User",
        on_delete=models.CASCADE,
        related_name="assigned_tasks",
    )
    assigned_by = models.ForeignKey(
        "signup.User",
        null=True,
        on_delete=models.SET_NULL,
        related_name="created_tasks",
    )
    deadline = models.DateField()
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default="medium")
    description = models.TextField()
    status = models.CharField(max_length=20, default="Pending")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["deadline", "-created_at"]

    def __str__(self):
        return self.title


class TaskSubmission(models.Model):
    STATUS_CHOICES = [
        ("Submitted", "Submitted"),
        ("Approved", "Approved"),
        ("RevisionRequested", "Revision Requested"),
    ]

    task = models.ForeignKey(
        Task,
        on_delete=models.CASCADE,
        related_name="submissions",
    )
    employee = models.ForeignKey(
        "signup.User",
        on_delete=models.CASCADE,
        related_name="task_submissions",
    )
    notes = models.TextField()
    reference_link = models.CharField(max_length=500, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="Submitted")
    submitted_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_note = models.TextField(blank=True)

    class Meta:
        ordering = ["-submitted_at"]
        constraints = [
            models.UniqueConstraint(fields=["task", "employee"], name="unique_task_submission"),
        ]

    def __str__(self):
        return f"{self.task.title} - {self.employee.fullName}"
