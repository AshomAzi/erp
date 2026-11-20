from django.test import TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from signup.models import User
from .models import Task, TaskSubmission


class ReviewSubmissionTests(TransactionTestCase):
    def setUp(self):
        self.supervisor = User.objects.create(
            fullName="Team Supervisor",
            email="supervisor@example.com",
            role="Supervisor",
            department="IT Support & Service Desk",
            password="hashed-password",
        )
        self.employee = User.objects.create(
            fullName="Team Member",
            email="employee@example.com",
            role="Employee",
            department="IT Support & Service Desk",
            password="hashed-password",
            mentor=self.supervisor,
        )
        self.task = Task.objects.create(
            title="Prepare report",
            assigned_to=self.employee,
            assigned_by=self.supervisor,
            deadline=timezone.localdate(),
            description="Complete the report.",
        )
        self.submission = TaskSubmission.objects.create(
            task=self.task,
            employee=self.employee,
            notes="Report completed.",
        )
        session = self.client.session
        session["user_id"] = self.supervisor.pk
        session.save()

    def test_supervisor_can_approve_submission(self):
        response = self.client.post(
            reverse(
                "review_submission",
                args=[self.submission.pk, "approve"],
            )
        )

        self.assertRedirects(response, reverse("supervisor"))
        self.submission.refresh_from_db()
        self.task.refresh_from_db()
        self.assertEqual(self.submission.status, "Approved")
        self.assertEqual(self.task.status, "Approved")
        self.assertIsNotNone(self.submission.reviewed_at)

    def test_supervisor_can_request_submission_revision(self):
        response = self.client.post(
            reverse(
                "review_submission",
                args=[self.submission.pk, "revision"],
            )
        )

        self.assertRedirects(response, reverse("supervisor"))
        self.submission.refresh_from_db()
        self.task.refresh_from_db()
        self.assertEqual(self.submission.status, "RevisionRequested")
        self.assertEqual(self.task.status, "Revision Requested")
        self.assertIsNotNone(self.submission.reviewed_at)

    def test_dashboard_only_lists_assigned_members_and_their_submissions(self):
        other_supervisor = User.objects.create(
            fullName="Other Supervisor",
            email="other-supervisor@example.com",
            role="Supervisor",
            department="IT Support & Service Desk",
            password="hashed-password",
        )
        other_employee = User.objects.create(
            fullName="Outside Team Member",
            email="outside@example.com",
            role="Employee",
            department="IT Support & Service Desk",
            password="hashed-password",
            mentor=other_supervisor,
        )
        other_task = Task.objects.create(
            title="Outside team report",
            assigned_to=other_employee,
            assigned_by=self.supervisor,
            deadline=timezone.localdate(),
            description="Not assigned to this supervisor's team.",
        )
        TaskSubmission.objects.create(
            task=other_task,
            employee=other_employee,
            notes="Outside team submission.",
        )

        response = self.client.get(reverse("supervisor"))

        self.assertContains(response, self.employee.fullName)
        self.assertContains(response, self.task.title)
        self.assertNotContains(response, other_employee.fullName)
        self.assertNotContains(response, other_task.title)

    def test_supervisor_cannot_assign_a_task_to_an_unassigned_member(self):
        other_supervisor = User.objects.create(
            fullName="Other Supervisor",
            email="other-supervisor@example.com",
            role="Supervisor",
            department="IT Support & Service Desk",
            password="hashed-password",
        )
        other_employee = User.objects.create(
            fullName="Outside Team Member",
            email="outside@example.com",
            role="Employee",
            department="IT Support & Service Desk",
            password="hashed-password",
            mentor=other_supervisor,
        )

        response = self.client.post(
            reverse("create_task"),
            {
                "title": "Unauthorized task",
                "assignee_id": other_employee.pk,
                "deadline": timezone.localdate().isoformat(),
                "priority": "medium",
                "description": "Should not be created.",
            },
        )

        self.assertRedirects(response, reverse("supervisor"))
        self.assertFalse(Task.objects.filter(title="Unauthorized task").exists())

    def test_supervisor_cannot_review_a_non_team_member_submission(self):
        other_supervisor = User.objects.create(
            fullName="Other Supervisor",
            email="other-supervisor@example.com",
            role="Supervisor",
            department="IT Support & Service Desk",
            password="hashed-password",
        )
        other_employee = User.objects.create(
            fullName="Outside Team Member",
            email="outside@example.com",
            role="Employee",
            department="IT Support & Service Desk",
            password="hashed-password",
            mentor=other_supervisor,
        )
        other_task = Task.objects.create(
            title="Outside team report",
            assigned_to=other_employee,
            assigned_by=self.supervisor,
            deadline=timezone.localdate(),
            description="Not assigned to this supervisor's team.",
        )
        submission = TaskSubmission.objects.create(
            task=other_task,
            employee=other_employee,
            notes="Outside team submission.",
        )

        response = self.client.post(
            reverse("review_submission", args=[submission.pk, "approve"])
        )

        self.assertRedirects(response, reverse("supervisor"))
        submission.refresh_from_db()
        self.assertEqual(submission.status, "Submitted")
