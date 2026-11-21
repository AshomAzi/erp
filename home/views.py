from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.hashers import check_password
from django.contrib.auth import authenticate, get_user_model, login, logout
from admin_dashboard.models import AuditLog, Notification
from signup.models import User
from django.views.decorators.http import require_POST
from django.http import JsonResponse


def _login_into_django_admin(request, user_obj, raw_password):
    """
    The custom login form uses the signup.User table, but /admin/ only
    understands Django's own auth user. For custom Admins, make sure a
    matching Django staff/superuser exists and log them into it so the
    same browser session can open /admin/ as well.
    """
    django_user_model = get_user_model()
    email = user_obj.email

    django_user = (
        django_user_model.objects.filter(email__iexact=email).first()
        or django_user_model.objects.filter(username__iexact=email).first()
    )
    if django_user is None:
        django_user = django_user_model(username=email, email=email)

    django_user.first_name = (user_obj.fullName or "")[:150]
    django_user.is_active = True
    django_user.is_staff = True
    django_user.is_superuser = True
    if not django_user.has_usable_password() or not django_user.check_password(raw_password):
        django_user.set_password(raw_password)
    django_user.save()

    login(
        request,
        django_user,
        backend="django.contrib.auth.backends.ModelBackend",
    )


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

        # Log custom Admins into Django's auth too, so /admin/ works.
        # Must run BEFORE the custom session keys below, because login()
        # can cycle/flush the session.
        if user_obj.role.strip().casefold() == "admin":
            _login_into_django_admin(request, user_obj, password)

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


@require_POST
def mark_notifications_read(request):
    user_id = request.session.get("user_id")
    if not user_id:
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return JsonResponse({"error": "Authentication required."}, status=403)
        return redirect("access_denied")

    user_obj = User.objects.filter(pk=user_id).first()
    if user_obj is None:
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return JsonResponse({"error": "User not found."}, status=403)
        return redirect("access_denied")

    Notification.objects.filter(recipient=user_obj, is_read=False).update(is_read=True)

    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JsonResponse({"status": "ok"})

    referer = request.META.get("HTTP_REFERER")
    if referer:
        return redirect(referer)
    return redirect("home")