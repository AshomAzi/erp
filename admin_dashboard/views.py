from datetime import datetime
import logging
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from employee.models import Attendance, LeaveRequest
from signup.models import User
from supervisor.models import Task

from .models import AuditLog, Department, Notification, OrganizationSettings


logger = logging.getLogger(__name__)

_DEPT_HAS_HEAD = any(
    getattr(field, "name", None) == "head" for field in Department._meta.get_fields()
)

# Only these roles may be assigned as a department head (no Intern / Employee).
HEAD_ELIGIBLE_ROLES = {"admin", "hr", "supervisor"}


def _is_head_eligible(user):
    return (user.role or "").strip().casefold() in HEAD_ELIGIBLE_ROLES


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

    users = list(User.objects.all().order_by("fullName"))
    if _DEPT_HAS_HEAD:
        departments = list(Department.objects.select_related("head").order_by("name"))
    else:
        departments = list(Department.objects.order_by("name"))

    dept_counts = {}
    for u in users:
        key = (u.department or "").strip().casefold()
        if key:
            dept_counts[key] = dept_counts.get(key, 0) + 1

    department_rows = []
    for dept in departments:
        head_obj = getattr(dept, "head", None) if _DEPT_HAS_HEAD else None
        department_rows.append(
            {
                "id": dept.pk,
                "name": dept.name,
                "head": head_obj,
                "head_id": head_obj.pk if head_obj else "",
                "head_name": head_obj.fullName if head_obj else "Not assigned",
                "member_count": dept_counts.get(dept.name.strip().casefold(), 0),
            }
        )

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
            "head_candidates": [u for u in users if _is_head_eligible(u)],
            "departments": departments,
            "department_rows": department_rows,
            "dept_has_head": _DEPT_HAS_HEAD,
            "total_users": len(users),
            "admin_count": sum(1 for u in users if (u.role or "").strip().casefold() == "admin"),
            "hr_count": sum(1 for u in users if (u.role or "").strip().casefold() == "hr"),
            "supervisor_count": sum(1 for u in users if (u.role or "").strip().casefold() == "supervisor"),
            "employee_count": sum(1 for u in users if (u.role or "").strip().casefold() == "employee"),
            "intern_count": sum(1 for u in users if (u.role or "").strip().casefold() == "intern"),
            "pending_approvals_count": sum(1 for u in users if not u.is_approved),
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
    department_raw = request.POST.get("department", "").strip()
    role = request.POST.get("role", "Employee").strip()
    password = request.POST.get("password", "")

    valid_roles = {"Admin", "HR", "Supervisor", "Employee", "Intern"}
    if not full_name or not email or role not in valid_roles:
        messages.error(request, "Provide a valid full name, email, and role.")
        return redirect("admin_dashboard")

    department_obj = Department.objects.filter(name__iexact=department_raw).first()
    if not department_raw or department_obj is None:
        messages.error(request, "Choose a valid department.")
        return redirect("admin_dashboard")

    department = department_obj.name

    if not password.strip():
        messages.error(request, "A password is required to create a user.")
        return redirect("admin_dashboard")
    if len(password) < 8:
        messages.error(request, "Password must be at least 8 characters long.")
        return redirect("admin_dashboard")

    if User.objects.filter(email__iexact=email).exists():
        messages.error(request, "A user with that email already exists.")
        return redirect("admin_dashboard")

    with transaction.atomic():
        new_user = User.objects.create(
            fullName=full_name,
            email=email,
            department=department,
            role=role,
            password=make_password(password),
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

    if (target_user.role or "").strip().casefold() == "admin":
        messages.error(request, "Admin roles cannot be modified.")
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
def reset_user_password(request):
    admin_user = _get_admin_user(request)
    if admin_user is None:
        return redirect("access_denied")

    try:
        target_id = int(request.POST.get("user_id", ""))
    except (TypeError, ValueError):
        messages.error(request, "Select a valid user.")
        return redirect("admin_dashboard")

    password = request.POST.get("password", "")
    if not password.strip():
        messages.error(request, "Enter a new password.")
        return redirect("admin_dashboard")
    if len(password) < 8:
        messages.error(request, "Password must be at least 8 characters long.")
        return redirect("admin_dashboard")

    target_user = User.objects.filter(pk=target_id).first()
    if target_user is None:
        messages.error(request, "User not found.")
        return redirect("admin_dashboard")

    with transaction.atomic():
        target_user.password = make_password(password)
        target_user.save(update_fields=["password"])

        # Keep the matching Django admin account (if any) in step.
        django_user = get_user_model().objects.filter(email__iexact=target_user.email).first()
        if django_user is not None:
            django_user.set_password(password)
            django_user.save(update_fields=["password"])

        AuditLog.objects.create(
            actor=admin_user,
            action="Password reset",
            target=f"{target_user.fullName} ({target_user.email})",
        )
        Notification.objects.create(
            recipient=target_user,
            message="Your password was reset by an administrator.",
            link="/",
        )

    messages.success(request, f"Password reset for {target_user.fullName}.")
    return redirect("admin_dashboard")


@require_POST
def create_department(request):
    admin_user = _get_admin_user(request)
    if admin_user is None:
        return redirect("access_denied")

    dept_name = (request.POST.get("department_name") or request.POST.get("name") or "").strip()
    if not dept_name:
        messages.error(request, "Enter a department name.")
        return redirect("admin_dashboard")

    head_id = (request.POST.get("head_id") or "").strip()
    head_user = User.objects.filter(pk=head_id).first() if (head_id and _DEPT_HAS_HEAD) else None
    if head_user is not None and not _is_head_eligible(head_user):
        messages.error(request, "A department head must be an Admin, HR, or Supervisor.")
        return redirect("admin_dashboard")

    try:
        with transaction.atomic():
            existing = Department.objects.filter(name__iexact=dept_name).first()
            if existing is None:
                create_kwargs = {"name": dept_name}
                if _DEPT_HAS_HEAD:
                    create_kwargs["head"] = head_user
                dept = Department.objects.create(**create_kwargs)
            else:
                dept = existing
                if _DEPT_HAS_HEAD and head_id and getattr(dept, "head_id", None) != (head_user.pk if head_user else None):
                    dept.head = head_user
                    dept.save(update_fields=["head"])

            target_desc = dept.name
            if _DEPT_HAS_HEAD and head_user:
                target_desc = f"{dept.name} (Head: {head_user.fullName})"

            AuditLog.objects.create(
                actor=admin_user,
                action="Department created",
                target=target_desc,
            )
            _notify_admins(f"Department '{dept.name}' was created by {admin_user.fullName}.")
    except IntegrityError:
        messages.error(request, f"A department named '{dept_name}' already exists.")
        return redirect("admin_dashboard")

    messages.success(request, f"Department '{dept.name}' saved.")
    return redirect("admin_dashboard")


@require_POST
def update_department(request):
    admin_user = _get_admin_user(request)
    if admin_user is None:
        return redirect("access_denied")

    dept_id = (request.POST.get("department_id") or "").strip()
    old_name = (request.POST.get("old_department") or "").strip()
    new_name = (
        request.POST.get("department_name")
        or request.POST.get("name")
        or request.POST.get("department")
        or ""
    ).strip()
    head_id_raw = request.POST.get("head_id")
    clear_head = request.POST.get("clear_head") == "1"
    user_id_raw = (request.POST.get("user_id") or "").strip()

    head_user = None
    if _DEPT_HAS_HEAD and head_id_raw and not clear_head:
        head_user = User.objects.filter(pk=head_id_raw).first()
        if head_user is not None and not _is_head_eligible(head_user):
            messages.error(request, "A department head must be an Admin, HR, or Supervisor.")
            return redirect("admin_dashboard")

    with transaction.atomic():
        dept_obj = None
        if dept_id:
            dept_obj = get_object_or_404(Department, pk=dept_id)
        elif old_name:
            dept_obj = Department.objects.filter(name__iexact=old_name).first()
        elif new_name and not user_id_raw:
            dept_obj = Department.objects.filter(name__iexact=new_name).first()

        resolved_dept_name = new_name or (dept_obj.name if dept_obj else "")

        if dept_obj is not None:
            previous_name = dept_obj.name
            if resolved_dept_name:
                conflict = (
                    Department.objects.filter(name__iexact=resolved_dept_name)
                    .exclude(pk=dept_obj.pk)
                    .first()
                )
                if conflict:
                    messages.error(request, f"A department named '{resolved_dept_name}' already exists.")
                    return redirect("admin_dashboard")
                dept_obj.name = resolved_dept_name

            update_fields = ["name"]
            if _DEPT_HAS_HEAD and (clear_head or head_id_raw is not None):
                dept_obj.head = None if clear_head else head_user
                update_fields.append("head")

            dept_obj.save(update_fields=update_fields)

            if previous_name != dept_obj.name:
                User.objects.filter(department__iexact=previous_name).update(department=dept_obj.name)

            resolved_dept_name = dept_obj.name
            AuditLog.objects.create(
                actor=admin_user,
                action="Department updated",
                target=f"{previous_name} -> {dept_obj.name}",
            )
            _notify_admins(f"Department updated to '{dept_obj.name}' by {admin_user.fullName}.")
        elif resolved_dept_name and not user_id_raw:
            create_kwargs = {"name": resolved_dept_name}
            if _DEPT_HAS_HEAD:
                create_kwargs["head"] = head_user
            dept_obj, _ = Department.objects.get_or_create(
                name__iexact=resolved_dept_name,
                defaults=create_kwargs,
            )
            resolved_dept_name = dept_obj.name
            AuditLog.objects.create(
                actor=admin_user,
                action="Department updated",
                target=f"{old_name or 'Department'} -> {resolved_dept_name}",
            )
            _notify_admins(f"Department updated to '{resolved_dept_name}' by {admin_user.fullName}.")

        if user_id_raw:
            target_user = User.objects.filter(pk=user_id_raw).first()
            if target_user is None:
                messages.error(request, "Selected user was not found.")
                return redirect("admin_dashboard")
            if not resolved_dept_name:
                messages.error(request, "Choose a department for the selected user.")
                return redirect("admin_dashboard")

            matched_dept = Department.objects.filter(name__iexact=resolved_dept_name).first()
            final_dept_name = matched_dept.name if matched_dept else resolved_dept_name
            target_user.department = final_dept_name
            target_user.save(update_fields=["department"])

            AuditLog.objects.create(
                actor=admin_user,
                action="User department assigned",
                target=f"{target_user.fullName} -> {final_dept_name}",
            )
            Notification.objects.create(
                recipient=target_user,
                message=f"Your department has been updated to {final_dept_name} by {admin_user.fullName}.",
                link="/",
            )
            _notify_admins(
                f"Assigned {target_user.fullName} to department '{final_dept_name}' by {admin_user.fullName}."
            )
            messages.success(request, f"Assigned {target_user.fullName} to {final_dept_name}.")
            return redirect("admin_dashboard")

        if not resolved_dept_name:
            messages.error(request, "Enter a valid department name.")
            return redirect("admin_dashboard")

    messages.success(request, f"Department '{resolved_dept_name}' updated.")
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
        settings_obj.updated_by = admin_user
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