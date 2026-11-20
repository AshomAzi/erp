from datetime import time

from django.db import models
from django.db.models.functions import Lower


class Department(models.Model):
    name = models.CharField(max_length=50)
    head = models.ForeignKey(
        "signup.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="headed_departments",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(Lower("name"), name="unique_department_name_ci"),
        ]

    def __str__(self):
        return self.name


class AuditLog(models.Model):
    actor = models.ForeignKey(
        "signup.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_events",
    )
    action = models.CharField(max_length=100)
    target = models.CharField(max_length=255)
    occurred_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-occurred_at"]

    def __str__(self):
        return f"{self.action}: {self.target}"


class OrganizationSettings(models.Model):
    organization_name = models.CharField(max_length=100, default="CoreERP Technologies Ltd.")
    check_in_time = models.TimeField(default=time(9, 0))
    check_out_time = models.TimeField(default=time(17, 0))
    updated_by = models.ForeignKey(
        "signup.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="organization_settings_updates",
    )
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.organization_name


class Notification(models.Model):
    recipient = models.ForeignKey(
        "signup.User",
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    message = models.CharField(max_length=255)
    link = models.CharField(max_length=255, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.message
