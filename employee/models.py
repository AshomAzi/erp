from django.db import models


class Attendance(models.Model):
    STATUS_CHOICES = [
        ("Present", "Present"),
        ("Late", "Late"),
    ]

    employee = models.ForeignKey(
        "signup.User",
        on_delete=models.CASCADE,
        related_name="attendance_records",
    )
    date = models.DateField()
    check_in = models.DateTimeField(null=True, blank=True)
    check_out = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="Present")

    class Meta:
        ordering = ["-date", "employee__fullName"]
        constraints = [
            models.UniqueConstraint(fields=["employee", "date"], name="unique_daily_attendance"),
        ]

    def __str__(self):
        return f"{self.employee.fullName} - {self.date}"


class LeaveRequest(models.Model):
    LEAVE_TYPE_CHOICES = [
        ("annual", "Annual Leave"),
        ("sick", "Sick Leave"),
        ("casual", "Casual / Personal Leave"),
    ]
    STATUS_CHOICES = [
        ("Pending", "Pending"),
        ("Approved", "Approved"),
        ("Rejected", "Rejected"),
    ]

    employee = models.ForeignKey(
        "signup.User",
        on_delete=models.CASCADE,
        related_name="leave_requests",
    )
    leave_type = models.CharField(max_length=20, choices=LEAVE_TYPE_CHOICES)
    start_date = models.DateField()
    end_date = models.DateField()
    reason = models.TextField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="Pending")
    requested_at = models.DateTimeField(auto_now_add=True)
    reviewed_by = models.ForeignKey(
        "signup.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reviewed_leave_requests",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-requested_at"]

    def get_leave_type_display(self) -> str:
        return dict(self.LEAVE_TYPE_CHOICES).get(self.leave_type, self.leave_type)

    def __str__(self):
        return f"{self.employee.fullName} - {self.get_leave_type_display()}"
