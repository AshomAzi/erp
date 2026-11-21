from dataclasses import dataclass
from datetime import date
import csv

from django.contrib import messages
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from admin_dashboard.models import AuditLog, Notification, OrganizationSettings
from employee.attendance_policy import attendance_deadlines
from employee.models import Attendance, LeaveRequest
from signup.models import User
from supervisor.models import Task


@dataclass(frozen=True)
class StaffDirectoryEntry:
    staff: User
    staff_id: str
    employment_type: str


def hr(request):
    user_id = request.session.get("user_id")
    user_obj = User.objects.filter(pk=user_id, role__iexact="HR").first()
    if user_obj is None:
        return redirect("access_denied")

    staff_members = list(
        User.objects.filter(role__in=["Employee", "Intern"])
        .select_related("mentor")
        .order_by("fullName")
    )
    mentors = User.objects.filter(role="Supervisor").order_by("fullName")
    organization_settings, _ = OrganizationSettings.objects.get_or_create(pk=1)
    today = timezone.localdate()
    now = timezone.localtime()
    late_deadline, absence_deadline = attendance_deadlines(
        organization_settings.check_in_time,
        today,
    )
    workforce = User.objects.filter(role__in=["Employee", "Intern"])
    present_today = Attendance.objects.filter(
        date=today,
        employee__role__in=["Employee", "Intern"],
        check_in__isnull=False,
    )
    approved_leave_users = LeaveRequest.objects.filter(
        status="Approved",
        start_date__lte=today,
        end_date__gte=today,
    ).values_list("employee_id", flat=True)
    absent_today = 0
    if today.weekday() < 5 and now > absence_deadline:
        absent_today = (
            workforce.exclude(pk__in=present_today.values_list("employee_id", flat=True))
            .exclude(pk__in=approved_leave_users)
            .count()
        )

    directory_entries = []
    for member in staff_members:
        is_intern = member.role == "Intern"
        prefix = "INT" if is_intern else "EMP"
        employment_type = "Intern" if is_intern else "Full-Time"
        directory_entries.append(
            StaffDirectoryEntry(
                staff=member,
                staff_id=f"{prefix}-{str(member.pk).zfill(3)}",
                employment_type=employment_type,
            )
        )

    notification_queryset = Notification.objects.filter(recipient_id=user_obj.pk).order_by("-created_at")
    notifications = notification_queryset[:10]
    unread_notification_count = notification_queryset.filter(is_read=False).count()

    return render(
        request,
        "hr_dashboard.html",
        {
            "user_obj": user_obj,
            "staff_members": directory_entries,
            "staff_options": staff_members,
            "mentor_options": mentors,
            "total_workforce": workforce.count(),
            "full_time_count": User.objects.filter(role="Employee").count(),
            "intern_count": User.objects.filter(role="Intern").count(),
            "present_today": present_today.count(),
            "late_today": present_today.filter(status="Late").count(),
            "late_after_time": late_deadline.time(),
            "absence_after_time": absence_deadline.time(),
            "pending_leaves": LeaveRequest.objects.filter(status="Pending").count(),
            "absent_today": absent_today,
            "organization_settings": organization_settings,
            "attendance_records": Attendance.objects.filter(date=today)
            .select_related("employee")
            .order_by("check_in"),
            "leave_requests": LeaveRequest.objects.select_related("employee")
            .order_by("-requested_at")[:20],
            "notifications": notifications,
            "unread_notification_count": unread_notification_count,
        },
    )


@require_POST
def assign_mentor(request):
    hr_user = User.objects.filter(
        pk=request.session.get("user_id"),
        role__iexact="HR",
    ).first()
    if hr_user is None:
        return redirect("access_denied")

    try:
        staff_id = int(request.POST.get("staff_id", ""))
        mentor_id = int(request.POST.get("mentor_id", ""))
    except (TypeError, ValueError):
        messages.error(request, "Select a valid staff member and supervisor.")
        return redirect("hr")

    staff_member = User.objects.filter(
        pk=staff_id,
        role__in=["Employee", "Intern"],
    ).first()
    mentor = User.objects.filter(pk=mentor_id, role="Supervisor").first()
    if staff_member is None or mentor is None:
        messages.error(request, "Select an available employee or intern and a supervisor mentor.")
        return redirect("hr")
    if staff_member.mentor == mentor:
        messages.info(request, "That supervisor is already assigned as this member's mentor.")
        return redirect("hr")

    with transaction.atomic():
        staff_member.mentor = mentor
        staff_member.save(update_fields=["mentor"])
        AuditLog.objects.create(
            actor=hr_user,
            action="Mentor assigned",
            target=f"{staff_member.fullName} -> {mentor.fullName}",
        )
        Notification.objects.create(
            recipient=staff_member,
            message=f"You have been assigned {mentor.fullName} as your supervisor mentor.",
            link="/epr/employee/",
        )
        Notification.objects.create(
            recipient=mentor,
            message=f"{staff_member.fullName} has been assigned to your mentorship.",
            link="/epr/supervisor/",
        )

    messages.success(request, f"{mentor.fullName} was assigned as {staff_member.fullName}'s mentor.")
    return redirect("hr")


@require_POST
def review_leave(request, leave_id, decision):
    hr_user = User.objects.filter(
        pk=request.session.get("user_id"),
        role__iexact="HR",
    ).first()
    if hr_user is None:
        return redirect("access_denied")
    if decision not in {"approve", "reject"}:
        messages.error(request, "Choose a valid leave decision.")
        return redirect("hr")

    with transaction.atomic():
        leave_request = get_object_or_404(
            LeaveRequest.objects.select_for_update().select_related("employee"),
            pk=leave_id,
        )
        if leave_request.status != "Pending":
            messages.info(request, "This leave request has already been reviewed.")
            return redirect("hr")

        leave_request.status = "Approved" if decision == "approve" else "Rejected"
        leave_request.reviewed_by = hr_user
        leave_request.reviewed_at = timezone.now()
        leave_request.save(update_fields=["status", "reviewed_by", "reviewed_at"])
        AuditLog.objects.create(
            actor=hr_user,
            action=f"Leave {leave_request.status.lower()}",
            target=f"{leave_request.employee.fullName}: {leave_request.get_leave_type_display()}",
        )
        Notification.objects.create(
            recipient=leave_request.employee,
            message=f"Your {leave_request.get_leave_type_display()} request was {leave_request.status.lower()}.",
            link="/epr/employee/",
        )

    messages.success(request, f"Leave request {leave_request.status.lower()}.")
    return redirect("hr")


@require_POST
def mark_notifications_read(request):
    user_id = request.session.get("user_id")
    if user_id:
        Notification.objects.filter(recipient_id=user_id, is_read=False).update(is_read=True)
    return HttpResponse(status=204)


def export_reports(request):
    hr_user = User.objects.filter(
        pk=request.session.get("user_id"),
        role__iexact="HR",
    ).first()
    if hr_user is None:
        return redirect("access_denied")

    report_type = request.GET.get("report_type", "monthly_attendance")
    month_value = request.GET.get("month", timezone.localdate().strftime("%Y-%m"))
    try:
        year, month = (int(part) for part in month_value.split("-", 1))
        month_start = date(year, month, 1)
        if month == 12:
            month_end = date(year + 1, 1, 1)
        else:
            month_end = date(year, month + 1, 1)
    except (TypeError, ValueError):
        month_start = timezone.localdate().replace(day=1)
        month_end = timezone.localdate()

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{report_type}_{month_value}.csv"'
    writer = csv.writer(response)

    if report_type == "leave_balances":
        writer.writerow(["Name", "Email", "Department", "Leave Type", "Start Date", "End Date", "Status"])
        for leave in LeaveRequest.objects.filter(
            start_date__gte=month_start,
            start_date__lt=month_end,
        ).select_related("employee"):
            writer.writerow([
                leave.employee.fullName,
                leave.employee.email,
                leave.employee.department,
                leave.get_leave_type_display(),
                leave.start_date.strftime("%Y-%m-%d") if leave.start_date else "",
                leave.end_date.strftime("%Y-%m-%d") if leave.end_date else "",
                leave.status,
            ])
    elif report_type == "intern_roster":
        writer.writerow(["Staff ID", "Name", "Email", "Department", "Date Joined", "Mentor"])
        for staff in User.objects.filter(role="Intern").select_related("mentor").order_by("fullName"):
            writer.writerow([
                f"INT-{str(staff.pk).zfill(3)}",
                staff.fullName,
                staff.email,
                staff.department,
                staff.date_joined.strftime("%Y-%m-%d") if staff.date_joined else "Not recorded",
                staff.mentor.fullName if staff.mentor else "Not assigned",
            ])
    elif report_type == "task_summary":
        writer.writerow(["Task Title", "Assignee", "Assigned By", "Priority", "Deadline", "Status", "Created At"])
        for task in Task.objects.filter(
            created_at__gte=month_start,
            created_at__lt=month_end,
        ).select_related("assigned_to", "assigned_by").order_by("-created_at"):
            priority_display = dict(Task.PRIORITY_CHOICES).get(task.priority, task.priority)
            writer.writerow([
                task.title,
                task.assigned_to.fullName,
                task.assigned_by.fullName if task.assigned_by else "System",
                priority_display,
                task.deadline.strftime("%Y-%m-%d") if task.deadline else "",
                task.status,
                task.created_at.strftime("%Y-%m-%d %H:%M") if task.created_at else "",
            ])
    elif report_type == "user_roster":
        writer.writerow(["Name", "Email", "Role", "Department", "Date Joined"])
        for user in User.objects.order_by("fullName"):
            writer.writerow([
                user.fullName,
                user.email,
                user.role,
                user.department,
                user.date_joined.strftime("%Y-%m-%d") if user.date_joined else "Not recorded",
            ])
    else:
        organization_settings, _ = OrganizationSettings.objects.get_or_create(pk=1)
        writer.writerow(["Name", "Email", "Department", "Date", "Check-In", "Check-Out", "Status"])
        attendance = Attendance.objects.filter(
            date__gte=month_start,
            date__lt=month_end,
        ).select_related("employee").order_by("date", "employee__fullName")
        if report_type == "lateness":
            attendance = attendance.filter(status="Late")
        for record in attendance:
            writer.writerow([
                record.employee.fullName,
                record.employee.email,
                record.employee.department,
                record.date.strftime("%Y-%m-%d") if record.date else "",
                record.check_in.strftime("%Y-%m-%d %H:%M") if record.check_in else "",
                record.check_out.strftime("%Y-%m-%d %H:%M") if record.check_out else "",
                record.status,
            ])
    return response