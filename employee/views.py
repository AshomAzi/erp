from django.contrib import messages
from django.db import transaction
from django.db.models import Prefetch
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_POST

from admin_dashboard.models import AuditLog, Notification, OrganizationSettings
from signup.models import User
from supervisor.models import Task, TaskSubmission

from .attendance_policy import attendance_deadlines, local_datetime
from .models import Attendance, LeaveRequest


def employee(request):
    user_id = request.session.get("user_id")
    user_obj = User.objects.filter(
        pk=user_id,
        role__in=["Employee", "Intern"],
    ).first() if user_id else None
    if user_obj is None:
        return redirect("access_denied")

    today = timezone.localdate()
    tasks = Task.objects.none()
    assigned_supervisor = user_obj.mentor
    if assigned_supervisor is not None:
        tasks = Task.objects.filter(
            assigned_to=user_obj,
            assigned_by=assigned_supervisor,
        ).select_related("assigned_by").prefetch_related(
            Prefetch(
                "submissions",
                queryset=TaskSubmission.objects.filter(employee_id=user_obj.pk),
                to_attr="employee_submissions",
            )
        )
    task_count = tasks.count()
    in_progress_count = tasks.filter(status__iexact="In Progress").count()
    pending_count = tasks.filter(status__iexact="Pending").count()
    attendance_records = Attendance.objects.filter(employee_id=user_obj.pk, date__lte=today).order_by("-date")
    attendance_count = attendance_records.count()
    present_count = attendance_records.filter(check_in__isnull=False).count()
    attendance_rate = round((present_count / attendance_count) * 100) if attendance_count else 0
    approved_leave_days = sum(
        (leave.end_date - leave.start_date).days + 1
        for leave in LeaveRequest.objects.filter(employee_id=user_obj.pk, status="Approved")
    )
    leave_balance = max(12 - approved_leave_days, 0)

    notification_queryset = Notification.objects.filter(recipient_id=user_obj.pk).order_by("-created_at")
    notifications = notification_queryset[:10]
    unread_notification_count = notification_queryset.filter(is_read=False).count()

    organization_settings, _ = OrganizationSettings.objects.get_or_create(pk=1)
    server_now = timezone.localtime()
    today_attendance = Attendance.objects.filter(employee_id=user_obj.pk, date=today).first()
    late_deadline, _ = attendance_deadlines(organization_settings.check_in_time, today)
    check_out_deadline = local_datetime(today, organization_settings.check_out_time)
    attendance_status = "Not Checked In"
    attendance_status_class = "badge-info"

    if today_attendance is not None:
        attendance_status = today_attendance.status
        attendance_status_class = (
            "badge-warning" if today_attendance.status == "Late" else "badge-success"
        )
        if today_attendance.check_out:
            attendance_status = f"Checked Out ({today_attendance.status})"
        elif today_attendance.check_in:
            attendance_status = f"Checked In ({today_attendance.status})"

    return render(
        request,
        "employee_dashboard.html",
        {
            "user_obj": user_obj,
            "tasks": tasks,
            "task_count": task_count,
            "in_progress_count": in_progress_count,
            "pending_count": pending_count,
            "attendance_rate": attendance_rate,
            "leave_balance": leave_balance,
            "notifications": notifications,
            "unread_notification_count": unread_notification_count,
            "organization_settings": organization_settings,
            "today_attendance": today_attendance,
            "attendance_records": Attendance.objects.filter(
                employee_id=user_obj.pk,
                date__lte=today,
            )[:5],
            "leave_requests": LeaveRequest.objects.filter(employee_id=user_obj.pk)[:10],
            "attendance_status": attendance_status,
            "attendance_status_class": attendance_status_class,
            "late_after_time": late_deadline.time(),
            "server_now_ms": int(server_now.timestamp() * 1000),
            "late_deadline_ms": int(late_deadline.timestamp() * 1000),
            "check_out_deadline_ms": int(check_out_deadline.timestamp() * 1000),
        },
    )


@require_POST
def record_attendance(request):
    employee_user = User.objects.filter(
        pk=request.session.get("user_id"),
        role__in=["Employee", "Intern"],
    ).first()
    if employee_user is None:
        return redirect("access_denied")

    action = request.POST.get("action")
    if action not in {"check_in", "check_out"}:
        messages.error(request, "Choose a valid attendance action.")
        return redirect("employee")

    organization_settings, _ = OrganizationSettings.objects.get_or_create(pk=1)
    today = timezone.localdate()
    now = timezone.localtime()

    with transaction.atomic():
        if action == "check_in":
            attendance, _ = Attendance.objects.select_for_update().get_or_create(
                employee=employee_user,
                date=today,
            )
            if attendance.check_in is not None:
                messages.error(request, "You have already checked in today.")
                return redirect("employee")

            late_deadline, _ = attendance_deadlines(organization_settings.check_in_time, today)
            attendance.check_in = now
            attendance.status = "Late" if now > late_deadline else "Present"
            attendance.save(update_fields=["check_in", "status"])
            audit_action = "Attendance check-in"
        else:
            attendance = Attendance.objects.select_for_update().filter(
                employee=employee_user,
                date=today,
            ).first()
            if attendance is None or attendance.check_in is None:
                messages.error(request, "Check in before checking out.")
                return redirect("employee")
            if attendance.check_out is not None:
                messages.error(request, "You have already checked out today.")
                return redirect("employee")

            check_out_deadline = local_datetime(today, organization_settings.check_out_time)
            if now < check_out_deadline:
                messages.error(
                    request,
                    f"Check-out is available at {organization_settings.check_out_time.strftime('%I:%M %p').lstrip('0')}.",
                )
                return redirect("employee")
            attendance.check_out = now
            attendance.save(update_fields=["check_out"])
            audit_action = "Attendance check-out"

        AuditLog.objects.create(
            actor=employee_user,
            action=audit_action,
            target=f"{employee_user.fullName} at {now.strftime('%H:%M')}",
        )

    messages.success(request, "Attendance recorded successfully.")
    return redirect("employee")


@require_POST
def request_leave(request):
    employee_user = User.objects.filter(
        pk=request.session.get("user_id"),
        role__in=["Employee", "Intern"],
    ).first()
    if employee_user is None:
        return redirect("access_denied")

    leave_type = request.POST.get("leave_type", "").strip()
    start_date = parse_date(request.POST.get("start_date", ""))
    end_date = parse_date(request.POST.get("end_date", ""))
    reason = request.POST.get("reason", "").strip()
    if leave_type not in dict(LeaveRequest.LEAVE_TYPE_CHOICES):
        messages.error(request, "Choose a valid leave type.")
        return redirect("employee")
    if start_date is None or end_date is None or start_date > end_date:
        messages.error(request, "Enter a valid leave date range.")
        return redirect("employee")
    if start_date < timezone.localdate():
        messages.error(request, "Leave cannot start in the past.")
        return redirect("employee")
    if not reason:
        messages.error(request, "Enter a reason for your leave request.")
        return redirect("employee")

    with transaction.atomic():
        leave_request = LeaveRequest.objects.create(
            employee=employee_user,
            leave_type=leave_type,
            start_date=start_date,
            end_date=end_date,
            reason=reason,
        )
        AuditLog.objects.create(
            actor=employee_user,
            action="Leave requested",
            target=f"{employee_user.fullName}: {leave_request.get_leave_type_display()}",
        )
        for hr in User.objects.filter(role__iexact="HR"):
            Notification.objects.create(
                recipient=hr,
                message=f"{employee_user.fullName} requested {leave_request.get_leave_type_display()}.",
                link="/epr/hr/",
            )

    messages.success(request, "Leave request submitted for HR review.")
    return redirect("employee")


@require_POST
def start_task(request, task_id):
    employee_user = User.objects.filter(
        pk=request.session.get("user_id"),
        role__in=["Employee", "Intern"],
    ).first()
    if employee_user is None:
        return redirect("access_denied")

    assigned_supervisor = employee_user.mentor
    if assigned_supervisor is None:
        messages.error(request, "You do not have a supervisor assigned.")
        return redirect("employee")

    with transaction.atomic():
        task = Task.objects.select_for_update().filter(
            pk=task_id,
            assigned_to=employee_user,
            assigned_by=assigned_supervisor,
        ).first()
        if task is None:
            messages.error(request, "Choose an assigned task.")
            return redirect("employee")
        if TaskSubmission.objects.filter(task=task, employee=employee_user).exists():
            messages.info(request, "This task has already been submitted.")
            return redirect("employee")
        if task.status != "Pending":
            messages.info(request, f"This task is already {task.status.lower()}.")
            return redirect("employee")

        task.status = "In Progress"
        task.save(update_fields=["status"])
        AuditLog.objects.create(
            actor=employee_user,
            action="Task started",
            target=f"{task.title} by {employee_user.fullName}",
        )
        Notification.objects.create(
            recipient=assigned_supervisor,
            message=f"{employee_user.fullName} started working on '{task.title}'.",
            link="/epr/supervisor/",
        )

    messages.success(request, "Task marked as in progress.")
    return redirect("employee")


@require_POST
def submit_task(request, task_id):
    employee_user = User.objects.filter(
        pk=request.session.get("user_id"),
        role__in=["Employee", "Intern"],
    ).first()
    if employee_user is None:
        return redirect("access_denied")

    assigned_supervisor = employee_user.mentor
    if assigned_supervisor is None:
        messages.error(request, "You do not have a supervisor assigned.")
        return redirect("employee")

    task = Task.objects.filter(
        pk=task_id,
        assigned_to=employee_user,
        assigned_by=assigned_supervisor,
    ).select_related("assigned_by").first()
    if task is None:
        messages.error(request, "Choose an assigned task.")
        return redirect("employee")

    notes = request.POST.get("notes", "").strip()
    reference_link = request.POST.get("reference_link", "").strip()
    if not notes:
        messages.error(request, "Add a summary of your completed work.")
        return redirect("employee")
    if len(reference_link) > 500:
        messages.error(request, "The reference link is too long.")
        return redirect("employee")

    with transaction.atomic():
        existing_submission = TaskSubmission.objects.select_for_update().filter(
            task=task,
            employee=employee_user,
        ).first()
        if existing_submission and existing_submission.status != "RevisionRequested":
            messages.error(
                request,
                "A submission can only be edited after a revision has been requested.",
            )
            return redirect("employee")

        _, created = TaskSubmission.objects.update_or_create(
            task=task,
            employee=employee_user,
            defaults={
                "notes": notes,
                "reference_link": reference_link,
                "status": "Submitted",
                "submitted_at": timezone.now(),
                "reviewed_at": None,
                "review_note": "",
            },
        )
        task.status = "Submitted"
        task.save(update_fields=["status"])
        AuditLog.objects.create(
            actor=employee_user,
            action="Task submitted",
            target=f"{task.title} by {employee_user.fullName}",
        )
        if task.assigned_by is not None:
            Notification.objects.create(
                recipient=task.assigned_by,
                message=f"{employee_user.fullName} submitted work for '{task.title}'.",
                link="/epr/supervisor/",
            )

    messages.success(
        request,
        "Task submitted successfully." if created else "Task submission updated successfully.",
    )
    return redirect("employee")