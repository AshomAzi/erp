from django.test import TestCase
from django.urls import reverse

from signup.models import User


class UpdateUserRoleTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create(
            fullName="Administrator",
            email="admin@example.com",
            role="Admin",
            department="IT Support & Service Desk",
            password="hashed-password",
        )
        session = self.client.session
        session["user_id"] = self.admin.pk
        session.save()

    def test_admin_cannot_change_own_role(self):
        self.client.post(
            reverse("update_user_role"),
            {"user_id": self.admin.pk, "role": "Employee"},
        )

        self.admin.refresh_from_db()
        self.assertEqual(self.admin.role, "Admin")

    def test_admin_cannot_change_another_admin_role(self):
        other_admin = User.objects.create(
            fullName="Second Administrator",
            email="second-admin@example.com",
            role="Admin",
            department="IT Support & Service Desk",
            password="hashed-password",
        )

        self.client.post(
            reverse("update_user_role"),
            {"user_id": other_admin.pk, "role": "Employee"},
        )

        other_admin.refresh_from_db()
        self.assertEqual(other_admin.role, "Admin")

    def test_admin_can_still_change_non_admin_role(self):
        employee = User.objects.create(
            fullName="Staff Member",
            email="staff@example.com",
            role="Employee",
            department="IT Support & Service Desk",
            password="hashed-password",
        )

        self.client.post(
            reverse("update_user_role"),
            {"user_id": employee.pk, "role": "Supervisor"},
        )

        employee.refresh_from_db()
        self.assertEqual(employee.role, "Supervisor")
