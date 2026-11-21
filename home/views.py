from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth import authenticate, get_user_model
from admin_dashboard.models import AuditLog
from signup.models import User
from django.contrib.auth import logout
from django.views.decorators.http import require_POST


def home(request):
    if request.method == "POST":
        email = request.POST.get("email", "").strip()
        password = request.POST.get("password", "")

        if not email or not password:
            messages.error(request, "All fields are required!")
            return render(request, "login.html")

        django_user_model = get_user_model()
        django_user = django_user_model.objects.filter(email__iexact=email).first()
        if django_user is None:
            django_user = django_user_model.objects.filter(username__iexact=email).first()

        user_obj = None
        if django_user is not None and django_user.is_superuser:
            authenticated_user = authenticate(
                request,
                username=django_user.get_username(),
                password=password,
            )
            if authenticated_user is not None:
                django_email = django_user.email or django_user.get_username()
                user_obj = User.objects.filter(email__iexact=django_email).first()
                if user_obj is None:
                    user_obj = User.objects.create(
                        fullName=django_user.get_full_name() or django_user.get_username(),
                        email=django_email,
                        role="Admin",
                        department="IT Support & Service Desk",
                        password=django_user.password,
                        is_approved=True,
                    )
                elif not user_obj.is_approved:
                    user_obj.is_approved = True
                    user_obj.save(update_fields=["is_approved"])

        if user_obj is None:
            user_obj = User.objects.filter(email__iexact=email).first()
            if user_obj is None or not check_password(password, user_obj.password):
                messages.error(
                    request,
                    "Invalid email or password. Don't have an account? Create one.",
                )
                return render(request, "login.html")

        if not user_obj.is_approved:
            messages.warning(
                request,
                "Your account is awaiting administrator approval before you can log in.",
            )
            return render(request, "login.html")

        request.session["user_id"] = user_obj.pk
        request.session["user_fullName"] = user_obj.fullName
        request.session["user_email"] = user_obj.email
        request.session["user_role"] = user_obj.role
        request.session["user_department"] = user_obj.department
        AuditLog.objects.create(
            actor=user_obj,
            action="Successful login",
            target=user_obj.email,
        )

        dashboards = {
            "admin": "admin_dashboard",
            "hr": "hr",
            "employee": "employee",
            "supervisor": "supervisor",
            "intern": "employee",
        }
        dashboard = dashboards.get(user_obj.role.strip().casefold(), "access_denied")
        return redirect(dashboard)
    else:
        return render(request, "login.html")


def forgot_password(request):
    if request.method == "POST":
        email = request.POST.get("email", "").strip()
        password = request.POST.get("password", "")
        password_confirmation = request.POST.get("confirm_password", "")

        if len(password) < 8:
            messages.error(request, "Password must be at least 8 characters long.")
            return render(request, "forgot_password.html")
        if password != password_confirmation:
            messages.error(request, "Passwords do not match.")
            return render(request, "forgot_password.html")

        user_obj = User.objects.filter(email__iexact=email).first()
        if user_obj is None:
            messages.error(request, "No account uses that email address.")
            return render(request, "forgot_password.html")

        user_obj.password = make_password(password)
        user_obj.save(update_fields=["password"])
        messages.success(request, "Password updated. You can now sign in.")
        return redirect("home")

    return render(request, "forgot_password.html")

@require_POST
def logout_view(request):
    user_id = request.session.get("user_id")
    user_obj = User.objects.filter(pk=user_id).first() if user_id else None

    if user_obj is not None:
        AuditLog.objects.create(
            actor=user_obj,
            action="Logged out",
            target=user_obj.email,
        )

    logout(request)
    request.session.flush()
    messages.info(request, "You have been logged out.")
    return redirect("/")