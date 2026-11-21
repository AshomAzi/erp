from datetime import datetime

from django.contrib import messages
from django.contrib.auth.hashers import make_password
from django.db import transaction
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.crypto import get_random_string
from django.views.decorators.http import require_POST

from employee.models import Attendance, LeaveRequest
from signup.models import User
from supervisor.models import Task

from .models import AuditLog, Notification, OrganizationSettings


def _get_admin_user(request):
    return User.objects.filter(
        pk=request.session.get("user_id"),
        role__iexact="Admin",
    ).first()


def _notify_admins(message, link="/epr/admin_dashboard/"):
    for admin in User.objects.filter(role__iexact="Admin"):
        Notification.objects.create(
            recipient=admin,
            message=message,
            link=link,
        )


def admin_dashboard(request):
    user_obj = _get_admin_user(request)
    if user_obj is None:
        return redirect("access_denied")

    users = User.objects.all().order_by("fullName")
    audit_logs = AuditLog.objects.select_related("actor").order_by("-occurred_at")[:30]
    organization_settings, _ = OrganizationSettings.objects.get_or_create(pk=1)

    notification_queryset = Notification.objects.filter(recipient_id=user_obj.pk).order_by("-created_at")
    notifications = notification_queryset[:10]
    unread_notification_count = notification_queryset.filter(is_read=False).count()

    today = timezone.localdate()

    return render(
        request,
        "admin_dashboard.html",
        {
            "user_obj": user_obj,
            "users": users,
            "total_users": users.count(),
            "admin_count": users.filter(role__iexact="Admin").count(),
            "hr_count": users.filter(role__iexact="HR").count(),
            "supervisor_count": users.filter(role__iexact="Supervisor").count(),
            "employee_count": users.filter(role__iexact="Employee").count(),
            "intern_count": users.filter(role__iexact="Intern").count(),
            "pending_approvals_count": users.filter(is_approved=False).count(),
            "active_tasks": Task.objects.exclude(status="Approved").count(),
            "pending_leaves": LeaveRequest.objects.filter(status="Pending").count(),
            "present_today": Attendance.objects.filter(date=today, check_in__isnull=False).count(),
            "audit_logs": audit_logs,
            "organization_settings": organization_settings,
            "notifications": notifications,
            "unread_notification_count": unread_notification_count,
        },
    )


@require_POST
def create_user(request):
    admin_user = _get_admin_user(request)
    if admin_user is None:
        return redirect("access_denied")

    full_name = request.POST.get("full_name", "").strip()
    email = request.POST.get("email", "").strip().lower()
    department = request.POST.get("department", "").strip()
    role = request.POST.get("role", "Employee").strip()
    password = request.POST.get("password", "").strip()

    valid_roles = {"Admin", "HR", "Supervisor", "Employee", "Intern"}
    if not full_name or not email or role not in valid_roles:
        messages.error(request, "Provide a valid full name, email, and role.")
        return redirect("admin_dashboard")

    if User.objects.filter(email__iexact=email).exists():
        messages.error(request, "A user with that email already exists.")
        return redirect("admin_dashboard")

    raw_password = password if password else get_random_string(16)
    with transaction.atomic():
        new_user = User.objects.create(
            fullName=full_name,
            email=email,
            department=department or "General",
            role=role,
            password=make_password(raw_password),
            is_approved=True,
        )
        AuditLog.objects.create(
            actor=admin_user,
            action="User created",
            target=f"{new_user.fullName} ({new_user.role})",
        )
        _notify_admins(
            f"New user account created: {new_user.fullName} ({new_user.role}) by {admin_user.fullName}."
        )

    messages.success(request, f"Created user {new_user.fullName}.")
    return redirect("admin_dashboard")


@require_POST
def approve_user(request, user_id):
    admin_user = _get_admin_user(request)
    if admin_user is None:
        return redirect("access_denied")

    target_user = User.objects.filter(pk=user_id).first()
    if target_user is None:
        messages.error(request, "User not found.")
        return redirect("admin_dashboard")

    if target_user.is_approved:
        messages.info(request, f"{target_user.fullName}'s account is already approved.")
        return redirect("admin_dashboard")

    with transaction.atomic():
        target_user.is_approved = True
        target_user.save(update_fields=["is_approved"])
        AuditLog.objects.create(
            actor=admin_user,
            action="User approved",
            target=f"{target_user.fullName} ({target_user.role})",
        )
        Notification.objects.create(
            recipient=target_user,
            message="Your CoreERP account has been approved by an administrator. You can now log in.",
            link="/",
        )
        _notify_admins(
            f"Approved new user account: {target_user.fullName} ({target_user.role}) by {admin_user.fullName}."
        )

    messages.success(request, f"Approved {target_user.fullName}'s account.")
    return redirect("admin_dashboard")


@require_POST
def update_user_role(request):
    admin_user = _get_admin_user(request)
    if admin_user is None:
        return redirect("access_denied")

    try:
        target_user_id = int(request.POST.get("user_id", ""))
    except (TypeError, ValueError):
        messages.error(request, "Select a valid user.")
        return redirect("admin_dashboard")

    new_role = request.POST.get("role", "").strip()
    valid_roles = {"Admin", "HR", "Supervisor", "Employee", "Intern"}
    if new_role not in valid_roles:
        messages.error(request, "Choose a valid role.")
        return redirect("admin_dashboard")

    target_user = User.objects.filter(pk=target_user_id).first()
    if target_user is None:
        messages.error(request, "User not found.")
        return redirect("admin_dashboard")

    if target_user.pk == admin_user.pk and new_role != "Admin":
        messages.error(request, "You cannot remove your own Admin privileges.")
        return redirect("admin_dashboard")

    if target_user.role == new_role:
        messages.info(request, f"{target_user.fullName} already has the {new_role} role.")
        return redirect("admin_dashboard")

    old_role = target_user.role
    with transaction.atomic():
        target_user.role = new_role
        target_user.save(update_fields=["role"])
        AuditLog.objects.create(
            actor=admin_user,
            action="User role updated",
            target=f"{target_user.fullName}: {old_role} -> {new_role}",
        )
        Notification.objects.create(
            recipient=target_user,
            message=f"Your system role was updated from {old_role} to {new_role} by {admin_user.fullName}.",
            link="/",
        )
        _notify_admins(
            f"Role change: {target_user.fullName} updated from {old_role} to {new_role} by {admin_user.fullName}."
        )

    messages.success(request, f"Updated {target_user.fullName}'s role to {new_role}.")
    return redirect("admin_dashboard")


@require_POST
def create_department(request):
    admin_user = _get_admin_user(request)
    if admin_user is None:
        return redirect("access_denied")

    dept_name = request.POST.get("department_name", "").strip() or request.POST.get("name", "").strip()
    if not dept_name:
        messages.error(request, "Enter a department name.")
        return redirect("admin_dashboard")

    AuditLog.objects.create(
        actor=admin_user,
        action="Department created",
        target=dept_name,
    )
    _notify_admins(f"Department '{dept_name}' was created by {admin_user.fullName}.")
    messages.success(request, f"Department '{dept_name}' recorded.")
    return redirect("admin_dashboard")


@require_POST
def update_department(request):
    admin_user = _get_admin_user(request)
    if admin_user is None:
        return redirect("access_denied")

    old_name = request.POST.get("old_department", "").strip()
    new_name = request.POST.get("department_name", "").strip() or request.POST.get("name", "").strip()
    if not new_name:
        messages.error(request, "Enter a valid department name.")
        return redirect("admin_dashboard")

    with transaction.atomic():
        if old_name and old_name != new_name:
            User.objects.filter(department__iexact=old_name).update(department=new_name)
        AuditLog.objects.create(
            actor=admin_user,
            action="Department updated",
            target=f"{old_name or 'Department'} -> {new_name}",
        )
        _notify_admins(f"Department updated to '{new_name}' by {admin_user.fullName}.")

    messages.success(request, f"Department updated to '{new_name}'.")
    return redirect("admin_dashboard")


@require_POST
def save_organization_settings(request):
    admin_user = _get_admin_user(request)
    if admin_user is None:
        return redirect("access_denied")

    check_in_raw = request.POST.get("check_in_time", "").strip()
    check_out_raw = request.POST.get("check_out_time", "").strip()

    try:
        check_in_time = datetime.strptime(check_in_raw, "%H:%M").time()
        check_out_time = datetime.strptime(check_out_raw, "%H:%M").time()
    except ValueError:
        messages.error(request, "Enter valid shift check-in and check-out times.")
        return redirect("admin_dashboard")

    if check_in_time >= check_out_time:
        messages.error(request, "Check-out time must be later than check-in time.")
        return redirect("admin_dashboard")

    with transaction.atomic():
        settings_obj, _ = OrganizationSettings.objects.get_or_create(pk=1)
        settings_obj.check_in_time = check_in_time
        settings_obj.check_out_time = check_out_time
        settings_obj.save()

        AuditLog.objects.create(
            actor=admin_user,
            action="Organization settings updated",
            target=f"Shift {check_in_time.strftime('%H:%M')} - {check_out_time.strftime('%H:%M')}",
        )
        _notify_admins(
            f"Organization shift schedule updated ({check_in_time.strftime('%I:%M %p')} - {check_out_time.strftime('%I:%M %p')}) by {admin_user.fullName}."
        )

    messages.success(request, "Organization settings saved.")
    return redirect("admin_dashboard")