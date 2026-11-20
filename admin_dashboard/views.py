from dataclasses import dataclass
from django.contrib import messages
from django.contrib.auth.hashers import make_password
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, transaction
from django.shortcuts import redirect, render
from datetime import datetime
from django.views.decorators.http import require_POST
from .models import AuditLog, Department, OrganizationSettings
from signup.models import User


@dataclass(frozen=True)
class DepartmentSummary:
    department: Department
    member_count: int


# Create your views here.

def admin_dashboard(request):
    user_obj = User.objects.filter(
        pk=request.session.get("user_id"),
        role__iexact="Admin",
    ).first()
    if user_obj is None:
        return redirect("access_denied")

    users = User.objects.order_by("fullName", "email")
    audit_logs = AuditLog.objects.select_related("actor")[:10]
    departments = list(Department.objects.select_related("head"))
    organization_settings, _ = OrganizationSettings.objects.get_or_create(pk=1)
    total_user_count = User.objects.count()
    role_names = [label for _, label in User.ROLE_CHOICES]
    member_counts = {}
    for member_department in User.objects.values_list("department", flat=True):
        key = member_department.casefold()
        member_counts[key] = member_counts.get(key, 0) + 1
    department_summaries = [
        DepartmentSummary(
            department=department,
            member_count=member_counts.get(department.name.casefold(), 0),
        )
        for department in departments
    ]
    return render(
        request,
        "admin_dashboard.html",
        {
            "user_obj": user_obj,
            "users": users,
            "role_editable_users": users.exclude(role__iexact="Admin"),
            "audit_logs": audit_logs,
            "departments": departments,
            "department_summaries": department_summaries,
            "department_heads": users,
            "organization_settings": organization_settings,
            "total_user_count": total_user_count,
            "active_user_count": total_user_count,
            "department_count": len(departments),
            "role_count": len(role_names),
            "role_names": role_names,
        },
    )


@require_POST
def create_user(request):
    admin_user = User.objects.filter(
        pk=request.session.get("user_id"),
        role__iexact="Admin",
    ).first()
    if admin_user is None:
        return redirect("access_denied")

    full_name = request.POST.get("full_name", "").strip()
    email = request.POST.get("email", "").strip()
    role = request.POST.get("role", "").strip()
    department = request.POST.get("department", "").strip()
    password = request.POST.get("password", "")
    password_confirmation = request.POST.get("confirmPassword", "")

    if not all((full_name, email, role, department, password, password_confirmation)):
        messages.error(request, "All fields are required.")
        return redirect("admin_dashboard")

    if len(full_name) > 100 or len(email) > 254:
        messages.error(request, "The name or email address is too long.")
        return redirect("admin_dashboard")

    try:
        validate_email(email)
    except ValidationError:
        messages.error(request, "Enter a valid email address.")
        return redirect("admin_dashboard")

    if role not in dict(User.ROLE_CHOICES):
        messages.error(request, "Choose a valid role.")
        return redirect("admin_dashboard")

    department_obj = Department.objects.filter(name__iexact=department).first()
    if department_obj is None:
        messages.error(request, "Choose a valid department.")
        return redirect("admin_dashboard")

    if len(password) < 8:
        messages.error(request, "Password must be at least 8 characters long.")
        return redirect("admin_dashboard")

    if password != password_confirmation:
        messages.error(request, "Passwords do not match.")
        return redirect("admin_dashboard")

    if User.objects.filter(email__iexact=email).exists():
        messages.error(request, "Email is already taken.")
        return redirect("admin_dashboard")

    try:
        with transaction.atomic():
            member = User.objects.create(
                fullName=full_name,
                email=email,
                role=role,
                department=department_obj.name,
                password=make_password(password),
            )
            AuditLog.objects.create(
                actor=admin_user,
                action="Member account created",
                target=f"{member.fullName} ({member.email}) - {member.role}",
            )
    except IntegrityError:
        messages.error(request, "Email is already taken.")
        return redirect("admin_dashboard")

    messages.success(request, "New member account created successfully.")
    return redirect("admin_dashboard")


@require_POST
def update_user_role(request):
    admin_user = User.objects.filter(
        pk=request.session.get("user_id"),
        role__iexact="Admin",
    ).first()
    if admin_user is None:
        return redirect("access_denied")

    try:
        target_user_id = int(request.POST.get("user_id", ""))
    except (TypeError, ValueError):
        target_user_id = None
    role = request.POST.get("role", "").strip()
    if target_user_id is None:
        messages.error(request, "Choose a valid user.")
        return redirect("admin_dashboard")
    if role not in dict(User.ROLE_CHOICES):
        messages.error(request, "Choose a valid role.")
        return redirect("admin_dashboard")
    with transaction.atomic():
        target_user = User.objects.select_for_update().filter(pk=target_user_id).first()
        if target_user is None:
            messages.error(request, "Choose a valid user.")
            return redirect("admin_dashboard")
        if target_user.role.casefold() == "admin":
            messages.error(request, "Administrator roles cannot be changed.")
            return redirect("admin_dashboard")
        if target_user.role == role:
            messages.info(request, "The selected member already has that role.")
            return redirect("admin_dashboard")

        previous_role = target_user.role
        target_user.role = role
        target_user.save(update_fields=["role"])
        AuditLog.objects.create(
            actor=admin_user,
            action="Role changed",
            target=f"{target_user.fullName} ({target_user.email}): {previous_role} -> {role}",
        )

    messages.success(request, "Member role updated.")
    return redirect("admin_dashboard")


@require_POST
def create_department(request):
    admin_user = User.objects.filter(
        pk=request.session.get("user_id"),
        role__iexact="Admin",
    ).first()
    if admin_user is None:
        return redirect("access_denied")

    name = request.POST.get("name", "").strip()
    head_id = request.POST.get("head_id", "").strip()
    if not name:
        messages.error(request, "Department name is required.")
        return redirect("admin_dashboard")
    if len(name) > 50:
        messages.error(request, "Department name must be 50 characters or fewer.")
        return redirect("admin_dashboard")
    if Department.objects.filter(name__iexact=name).exists():
        messages.error(request, "A department with that name already exists.")
        return redirect("admin_dashboard")

    head = None
    if head_id:
        try:
            head_pk = int(head_id)
        except ValueError:
            messages.error(request, "Choose a valid department head.")
            return redirect("admin_dashboard")
        head = User.objects.filter(pk=head_pk).first()
        if head is None:
            messages.error(request, "Choose a valid department head.")
            return redirect("admin_dashboard")

    try:
        with transaction.atomic():
            department = Department.objects.create(name=name, head=head)
            AuditLog.objects.create(
                actor=admin_user,
                action="Department created",
                target=department.name,
            )
    except IntegrityError:
        messages.error(request, "A department with that name already exists.")
        return redirect("admin_dashboard")

    messages.success(request, "Department created successfully.")
    return redirect("admin_dashboard")


@require_POST
def update_department(request):
    admin_user = User.objects.filter(
        pk=request.session.get("user_id"),
        role__iexact="Admin",
    ).first()
    if admin_user is None:
        return redirect("access_denied")

    try:
        department_id = int(request.POST.get("department_id", ""))
    except (TypeError, ValueError):
        department_id = None
    department = Department.objects.filter(pk=department_id).first()
    name = request.POST.get("name", "").strip()
    head_id = request.POST.get("head_id", "").strip()
    if department is None:
        messages.error(request, "Choose a valid department.")
        return redirect("admin_dashboard")
    if not name or len(name) > 50:
        messages.error(request, "Department name must be 1 to 50 characters.")
        return redirect("admin_dashboard")
    if Department.objects.filter(name__iexact=name).exclude(pk=department.pk).exists():
        messages.error(request, "A department with that name already exists.")
        return redirect("admin_dashboard")

    head = None
    if head_id:
        try:
            head = User.objects.filter(pk=int(head_id)).first()
        except (TypeError, ValueError):
            head = None
        if head is None:
            messages.error(request, "Choose a valid department head.")
            return redirect("admin_dashboard")

    with transaction.atomic():
        department.name = name
        department.head = head
        department.save(update_fields=["name", "head"])
        AuditLog.objects.create(
            actor=admin_user,
            action="Department updated",
            target=department.name,
        )
    messages.success(request, "Department updated successfully.")
    return redirect("admin_dashboard")


@require_POST
def save_organization_settings(request):
    admin_user = User.objects.filter(
        pk=request.session.get("user_id"),
        role__iexact="Admin",
    ).first()
    if admin_user is None:
        return redirect("access_denied")

    organization_name = request.POST.get("org_name", "").strip()
    check_in_value = request.POST.get("checkin_time", "").strip()
    check_out_value = request.POST.get("checkout_time", "").strip()
    if not organization_name:
        messages.error(request, "Organization name is required.")
        return redirect("admin_dashboard")
    if len(organization_name) > 100:
        messages.error(request, "Organization name must be 100 characters or fewer.")
        return redirect("admin_dashboard")

    try:
        check_in_time = datetime.strptime(check_in_value, "%H:%M").time()
        check_out_time = datetime.strptime(check_out_value, "%H:%M").time()
    except ValueError:
        messages.error(request, "Enter valid check-in and check-out times.")
        return redirect("admin_dashboard")

    if check_out_time <= check_in_time:
        messages.error(request, "Check-out time must be later than check-in time.")
        return redirect("admin_dashboard")

    with transaction.atomic():
        settings_obj, _ = OrganizationSettings.objects.select_for_update().get_or_create(pk=1)
        previous_values = (
            settings_obj.organization_name,
            settings_obj.check_in_time,
            settings_obj.check_out_time,
        )
        new_values = (organization_name, check_in_time, check_out_time)
        if previous_values == new_values:
            messages.info(request, "Organization settings are unchanged.")
            return redirect("admin_dashboard")

        settings_obj.organization_name = organization_name
        settings_obj.check_in_time = check_in_time
        settings_obj.check_out_time = check_out_time
        settings_obj.updated_by = admin_user
        settings_obj.save()
        AuditLog.objects.create(
            actor=admin_user,
            action="Organization settings updated",
            target=(
                f"{organization_name}; check-in {check_in_time.strftime('%H:%M')}; "
                f"check-out {check_out_time.strftime('%H:%M')}"
            ),
        )

    messages.success(request, "Organization settings saved.")
    return redirect("admin_dashboard")