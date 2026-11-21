from django.contrib import messages
from django.db import transaction
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_POST

from admin_dashboard.models import AuditLog, Notification
from employee.models import Attendance
from signup.models import User

from .models import Task, TaskSubmission


def supervisor(request):
    user_obj = User.objects.filter(
        pk=request.session.get("user_id"),
        role__iexact="Supervisor",
    ).first()
    if user_obj is None:
        return redirect("access_denied")

    tasks = Task.objects.filter(
        assigned_by=user_obj,
        assigned_to__mentor=user_obj,
    ).select_related("assigned_to")
    members = User.objects.filter(
        role__in=["Employee", "Intern"],
        mentor=user_obj,
    ).order_by("fullName")
    submissions = TaskSubmission.objects.filter(
        task__assigned_by=user_obj,
        task__assigned_to__mentor=user_obj,
    ).select_related("task", "employee")
    today = timezone.localdate()
    team_stats = []
    for member in members:
        attendance = Attendance.objects.filter(employee=member, date=today).first()
        member_tasks = Task.objects.filter(assigned_to=member, assigned_by=user_obj)
        open_tasks = member_tasks.exclude(status="Approved").count()
        completed = member_tasks.filter(status="Approved").count()
        total = member_tasks.count()
        team_stats.append({
            "member": member,
            "attendance": attendance,
            "open_tasks": open_tasks,
            "completion_rate": round((completed / total) * 100) if total else 0,
        })

    notification_queryset = Notification.objects.filter(recipient_id=user_obj.pk).order_by("-created_at")
    notifications = notification_queryset[:10]
    unread_notification_count = notification_queryset.filter(is_read=False).count()

    return render(
        request,
        "supervisor_dashboard.html",
        {
            "user_obj": user_obj,
            "tasks": tasks,
            "members": members,
            "submissions": submissions,
            "pending_submissions": submissions.filter(status="Submitted").count(),
            "team_stats": team_stats,
            "team_count": len(team_stats),
            "active_task_count": tasks.exclude(status="Approved").count(),
            "notifications": notifications,
            "unread_notification_count": unread_notification_count,
        },
    )


@require_POST
def create_task(request):
    supervisor_user = User.objects.filter(
        pk=request.session.get("user_id"),
        role__iexact="Supervisor",
    ).first()
    if supervisor_user is None:
        return redirect("access_denied")

    title = request.POST.get("title", "").strip()
    try:
        assignee_id = int(request.POST.get("assignee_id", ""))
    except (TypeError, ValueError):
        assignee_id = None
    assignee = User.objects.filter(
        pk=assignee_id,
        role__in=["Employee", "Intern"],
        mentor=supervisor_user,
    ).first()
    deadline = parse_date(request.POST.get("deadline", ""))
    priority = request.POST.get("priority", "medium").strip()
    description = request.POST.get("description", "").strip()

    if not title or len(title) > 160 or not description or assignee is None or deadline is None:
        messages.error(request, "Provide a title, eligible member, valid deadline, and task instructions.")
        return redirect("supervisor")
    if priority not in dict(Task.PRIORITY_CHOICES):
        messages.error(request, "Choose a valid task priority.")
        return redirect("supervisor")

    with transaction.atomic():
        task = Task.objects.create(
            title=title,
            assigned_to=assignee,
            assigned_by=supervisor_user,
            deadline=deadline,
            priority=priority,
            description=description,
        )
        AuditLog.objects.create(
            actor=supervisor_user,
            action="Task assigned",
            target=f"{task.title} -> {assignee.fullName} ({assignee.email}), due {task.deadline}",
        )
        Notification.objects.create(
            recipient=assignee,
            message=f"New task assigned by {supervisor_user.fullName}: {task.title}",
            link="/epr/employee/",
        )

    messages.success(request, "Task assigned successfully.")
    return redirect("supervisor")


@require_POST
def review_submission(request, submission_id, decision):
    supervisor_user = User.objects.filter(
        pk=request.session.get("user_id"),
        role__iexact="Supervisor",
    ).first()
    if supervisor_user is None:
        return redirect("access_denied")
    if decision not in {"approve", "revision"}:
        messages.error(request, "Choose a valid review action.")
        return redirect("supervisor")

    review_note = request.POST.get("review_note", "").strip()
    with transaction.atomic():
        submission = TaskSubmission.objects.select_for_update().select_related(
            "task", "employee"
        ).filter(
            pk=submission_id,
            task__assigned_by=supervisor_user,
            task__assigned_to__mentor=supervisor_user,
        ).first()
        if submission is None:
            messages.error(request, "Submission not found.")
            return redirect("supervisor")

        submission.status = "Approved" if decision == "approve" else "RevisionRequested"
        submission.reviewed_at = timezone.now()
        submission.review_note = review_note
        submission.save(update_fields=["status", "reviewed_at", "review_note"])
        submission.task.status = "Approved" if decision == "approve" else "Revision Requested"
        submission.task.save(update_fields=["status"])
        AuditLog.objects.create(
            actor=supervisor_user,
            action=f"Task submission {submission.status.lower()}",
            target=f"{submission.task.title} - {submission.employee.fullName}",
        )
        Notification.objects.create(
            recipient=submission.employee,
            message=(
                f"Your submission for '{submission.task.title}' was approved."
                if decision == "approve"
                else f"Revision requested for '{submission.task.title}'."
            ),
            link="/epr/employee/",
        )

    messages.success(
        request,
        "Submission approved." if decision == "approve" else "Revision requested.",
    )
    return redirect("supervisor")