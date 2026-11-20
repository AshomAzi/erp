from datetime import date, datetime, time, timezone as datetime_timezone
from unittest.mock import patch

from django.conf import settings
from django.test import TestCase
from django.urls import reverse

from admin_dashboard.models import AuditLog, OrganizationSettings
from employee.models import Attendance, LeaveRequest
from signup.models import User


class HrWorkforceMetricsTests(TestCase):
    def setUp(self):
        self.day = date(2026, 11, 23)
        self.hr_user = self.create_user("hr@example.com", "HR")
        session = self.client.session
        session["user_id"] = self.hr_user.pk
        session.save()
        self.client.cookies[settings.SESSION_COOKIE_NAME] = session.session_key
        OrganizationSettings.objects.get_or_create(
            pk=1,
            defaults={"check_in_time": time(9), "check_out_time": time(17)},
        )

        self.present_employee = self.create_user("present@example.com", "Employee")
        self.on_leave_employee = self.create_user("leave@example.com", "Employee")
        self.absent_intern = self.create_user("absent@example.com", "Intern")
        self.present_intern = self.create_user("intern@example.com", "Intern")
        Attendance.objects.create(
            employee=self.present_employee,
            date=self.day,
            check_in=datetime(2026, 11, 23, 9, 31, tzinfo=datetime_timezone.utc),
            status="Late",
        )
        Attendance.objects.create(
            employee=self.present_intern,
            date=self.day,
            check_in=datetime(2026, 11, 23, 9, 0, tzinfo=datetime_timezone.utc),
            status="Present",
        )
        LeaveRequest.objects.create(
            employee=self.on_leave_employee,
            leave_type="annual",
            start_date=self.day,
            end_date=self.day,
            reason="Approved leave",
            status="Approved",
        )
        LeaveRequest.objects.create(
            employee=self.present_employee,
            leave_type="sick",
            start_date=self.day,
            end_date=self.day,
            reason="Awaiting review",
        )

    @staticmethod
    def create_user(email, role):
        return User.objects.create(
            fullName=email.split("@")[0],
            email=email,
            role=role,
            department="Software Engineering",
            password="unused",
        )

    @patch("hr.views.timezone.localdate")
    @patch("hr.views.timezone.localtime")
    def test_metrics_count_attendance_leave_and_absence(self, localtime, localdate):
        localdate.return_value = self.day
        localtime.return_value = datetime(
            2026, 11, 23, 10, 0, tzinfo=datetime_timezone.utc
        )

        response = self.client.get(reverse("hr"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["total_workforce"], 4)
        self.assertEqual(response.context["full_time_count"], 2)
        self.assertEqual(response.context["intern_count"], 2)
        self.assertEqual(response.context["present_today"], 2)
        self.assertEqual(response.context["late_today"], 1)
        self.assertEqual(response.context["pending_leaves"], 1)
        self.assertEqual(response.context["absent_today"], 1)

    @patch("hr.views.timezone.localdate")
    @patch("hr.views.timezone.localtime")
    def test_weekend_absences_are_not_counted(self, localtime, localdate):
        sunday = date(2026, 11, 22)
        localdate.return_value = sunday
        localtime.return_value = datetime(
            2026, 11, 22, 10, 0, tzinfo=datetime_timezone.utc
        )

        response = self.client.get(reverse("hr"))

        self.assertEqual(response.context["absent_today"], 0)

    @patch("hr.views.timezone.localdate")
    @patch("hr.views.timezone.localtime")
    def test_absence_is_not_counted_at_the_exact_deadline(self, localtime, localdate):
        localdate.return_value = self.day
        localtime.return_value = datetime(
            2026, 11, 23, 9, 59, tzinfo=datetime_timezone.utc
        )

        response = self.client.get(reverse("hr"))

        self.assertEqual(response.context["absent_today"], 0)

    def test_rejecting_leave_records_correct_audit_action(self):
        leave_request = LeaveRequest.objects.create(
            employee=self.absent_intern,
            leave_type="sick",
            start_date=self.day,
            end_date=self.day,
            reason="Medical appointment",
        )

        response = self.client.post(
            reverse("review_leave", args=[leave_request.pk, "reject"])
        )

        leave_request.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(leave_request.status, "Rejected")
        self.assertTrue(
            AuditLog.objects.filter(actor=self.hr_user, action="Leave rejected").exists()
        )
