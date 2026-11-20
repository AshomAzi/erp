from datetime import date, datetime, time, timedelta, timezone as datetime_timezone
from unittest.mock import patch

from django.conf import settings
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from admin_dashboard.models import OrganizationSettings
from signup.models import User
from supervisor.models import Task, TaskSubmission

from .attendance_policy import attendance_deadlines
from .models import Attendance, LeaveRequest


class AttendancePolicyTests(TestCase):
    def test_deadlines_follow_the_configured_shift_start(self):
        late_deadline, absence_deadline = attendance_deadlines(
            time(9, 0),
            date(2026, 11, 23),
        )

        self.assertEqual(late_deadline.time(), time(9, 30))
        self.assertEqual(absence_deadline.time(), time(9, 59))


class RecordAttendanceTests(TestCase):
    def setUp(self):
        self.day = date(2026, 11, 23)
        self.employee = User.objects.create(
            fullName="Test Employee",
            email="employee@example.com",
            role="Employee",
            department="Software Engineering",
            password="unused",
        )
        session = self.client.session
        session["user_id"] = self.employee.pk
        session.save()
        self.client.cookies[settings.SESSION_COOKIE_NAME] = session.session_key
        OrganizationSettings.objects.get_or_create(pk=1)

    @patch("employee.views.timezone.localdate")
    @patch("employee.views.timezone.localtime")
    def test_check_in_at_late_deadline_is_on_time(self, localtime, localdate):
        localdate.return_value = self.day
        localtime.return_value = datetime(
            2026, 11, 23, 9, 30, tzinfo=datetime_timezone.utc
        )

        response = self.client.post(
            reverse("record_attendance"),
            {"action": "check_in"},
        )

        self.assertEqual(response.status_code, 302)
        attendance = Attendance.objects.get(employee=self.employee, date=self.day)
        self.assertEqual(attendance.status, "Present")

    @patch("employee.views.timezone.localdate")
    @patch("employee.views.timezone.localtime")
    def test_check_in_after_late_deadline_is_late(self, localtime, localdate):
        localdate.return_value = self.day
        localtime.return_value = datetime(
            2026, 11, 23, 9, 31, tzinfo=datetime_timezone.utc
        )

        self.client.post(reverse("record_attendance"), {"action": "check_in"})

        attendance = Attendance.objects.get(employee=self.employee, date=self.day)
        self.assertEqual(attendance.status, "Late")

    @patch("employee.views.timezone.localdate")
    @patch("employee.views.timezone.localtime")
    def test_duplicate_check_in_does_not_create_another_record(self, localtime, localdate):
        localdate.return_value = self.day
        localtime.return_value = datetime(
            2026, 11, 23, 9, 0, tzinfo=datetime_timezone.utc
        )
        url = reverse("record_attendance")

        self.client.post(url, {"action": "check_in"})
        response = self.client.post(url, {"action": "check_in"})

        self.assertEqual(response.status_code, 302)
        self.assertEqual(Attendance.objects.filter(employee=self.employee).count(), 1)

    @patch("employee.views.timezone.localdate")
    @patch("employee.views.timezone.localtime")
    def test_checkout_is_rejected_before_configured_time(self, localtime, localdate):
        localdate.return_value = self.day
        localtime.return_value = datetime(
            2026, 11, 23, 16, 59, tzinfo=datetime_timezone.utc
        )
        attendance = Attendance.objects.create(
            employee=self.employee,
            date=self.day,
            check_in=datetime(2026, 11, 23, 9, 0, tzinfo=datetime_timezone.utc),
        )

        self.client.post(reverse("record_attendance"), {"action": "check_out"})

        attendance.refresh_from_db()
        self.assertIsNone(attendance.check_out)

    def test_dashboard_renders_attendance_and_leave_forms(self):
        response = self.client.get(reverse("employee"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No attendance records yet.")
        self.assertContains(response, 'name="action"')
        self.assertContains(response, 'name="leave_type"')

    def test_leave_request_is_saved_for_hr_review(self):
        start_date = timezone.localdate() + timedelta(days=1)

        response = self.client.post(
            reverse("request_leave"),
            {
                "leave_type": "annual",
                "start_date": start_date.isoformat(),
                "end_date": start_date.isoformat(),
                "reason": "Planned personal leave",
            },
        )

        self.assertEqual(response.status_code, 302)
        leave_request = LeaveRequest.objects.get(employee=self.employee)
        self.assertEqual(leave_request.status, "Pending")

    def test_leave_type_display_uses_choice_label_and_unknown_value_fallback(self):
        leave_request = LeaveRequest(
            employee=self.employee,
            leave_type="annual",
            start_date=self.day,
            end_date=self.day,
            reason="Planned leave",
        )

        self.assertEqual(leave_request.get_leave_type_display(), "Annual Leave")
        leave_request.leave_type = "custom"
        self.assertEqual(leave_request.get_leave_type_display(), "custom")


class SubmitTaskTests(TestCase):
    def setUp(self):
        self.supervisor = User.objects.create(
            fullName="Assigned Supervisor",
            email="assigned-supervisor@example.com",
            role="Supervisor",
            department="Software Engineering",
            password="unused",
        )
        self.employee = User.objects.create(
            fullName="Project Employee",
            email="project-employee@example.com",
            role="Employee",
            department="Software Engineering",
            password="unused",
            mentor=self.supervisor,
        )
        self.task = Task.objects.create(
            title="Complete project",
            assigned_to=self.employee,
            assigned_by=self.supervisor,
            deadline=timezone.localdate(),
            description="Finish the assigned project.",
        )
        session = self.client.session
        session["user_id"] = self.employee.pk
        session.save()

    def submit(self, notes):
        return self.client.post(
            reverse("submit_task", args=[self.task.pk]),
            {"notes": notes, "reference_link": ""},
        )

    def test_employee_can_submit_a_task_for_the_first_time(self):
        response = self.submit("Initial project summary")

        self.assertEqual(response.status_code, 302)
        submission = TaskSubmission.objects.get(task=self.task, employee=self.employee)
        self.assertEqual(submission.notes, "Initial project summary")
        self.assertEqual(submission.status, "Submitted")

    def test_employee_can_edit_and_resubmit_after_revision_is_requested(self):
        submission = TaskSubmission.objects.create(
            task=self.task,
            employee=self.employee,
            notes="Original project summary",
            status="RevisionRequested",
        )

        response = self.submit("Updated project summary")

        self.assertEqual(response.status_code, 302)
        submission.refresh_from_db()
        self.assertEqual(submission.notes, "Updated project summary")
        self.assertEqual(submission.status, "Submitted")
        self.assertIsNone(submission.reviewed_at)

    def test_employee_cannot_edit_a_submission_while_review_is_pending(self):
        submission = TaskSubmission.objects.create(
            task=self.task,
            employee=self.employee,
            notes="Original project summary",
        )

        response = self.submit("Changed project summary")

        self.assertEqual(response.status_code, 302)
        submission.refresh_from_db()
        self.assertEqual(submission.notes, "Original project summary")
        self.assertEqual(submission.status, "Submitted")

    def test_employee_cannot_edit_an_approved_submission(self):
        submission = TaskSubmission.objects.create(
            task=self.task,
            employee=self.employee,
            notes="Approved project summary",
            status="Approved",
        )

        response = self.submit("Changed project summary")

        self.assertEqual(response.status_code, 302)
        submission.refresh_from_db()
        self.assertEqual(submission.notes, "Approved project summary")
        self.assertEqual(submission.status, "Approved")

    def test_dashboard_shows_edit_action_after_revision_is_requested(self):
        TaskSubmission.objects.create(
            task=self.task,
            employee=self.employee,
            notes="Original project summary",
            status="RevisionRequested",
        )

        response = self.client.get(reverse("employee"))

        self.assertContains(response, "Edit &amp; Resubmit")
        self.assertContains(response, 'data-task-submission-notes="Original project summary"')

    def test_employee_only_sees_tasks_from_their_assigned_supervisor(self):
        other_supervisor = User.objects.create(
            fullName="Other Supervisor",
            email="other-supervisor@example.com",
            role="Supervisor",
            department="Software Engineering",
            password="unused",
        )
        Task.objects.create(
            title="Outside supervisor task",
            assigned_to=self.employee,
            assigned_by=other_supervisor,
            deadline=timezone.localdate(),
            description="Not assigned by the employee's supervisor.",
        )

        response = self.client.get(reverse("employee"))

        self.assertContains(response, self.task.title)
        self.assertContains(response, self.supervisor.fullName)
        self.assertNotContains(response, "Outside supervisor task")

    def test_employee_cannot_submit_a_task_from_another_supervisor(self):
        other_supervisor = User.objects.create(
            fullName="Other Supervisor",
            email="other-supervisor@example.com",
            role="Supervisor",
            department="Software Engineering",
            password="unused",
        )
        other_task = Task.objects.create(
            title="Outside supervisor task",
            assigned_to=self.employee,
            assigned_by=other_supervisor,
            deadline=timezone.localdate(),
            description="Not assigned by the employee's supervisor.",
        )

        response = self.client.post(
            reverse("submit_task", args=[other_task.pk]),
            {"notes": "Should not submit", "reference_link": ""},
        )

        self.assertRedirects(response, reverse("employee"))
        self.assertFalse(TaskSubmission.objects.filter(task=other_task).exists())
