from django.shortcuts import render, redirect
from django.contrib import messages
from django.db import IntegrityError, transaction
from .models import User
from django.contrib.auth.hashers import make_password
from admin_dashboard.models import AuditLog, Department

# Create your views here.

def signup(request):
    departments = Department.objects.order_by("name")

    if request.method == "POST":
        fullName = request.POST.get("fullName", "").strip()
        email = request.POST.get("email", "").strip()
        role = request.POST.get("role", "").strip()
        department = request.POST.get("department", "").strip()
        password = request.POST.get("password", "")
        password2 = request.POST.get("confirmPassword", "")

        if not fullName or not email or not department or not role or not password or not password2:
            messages.error(request, "All fields are required.")
            return render(request, "signup.html", {"departments": departments})

        department_obj = Department.objects.filter(name__iexact=department).first()
        if department_obj is None:
            messages.error(request, "Choose a valid department")    
            return render(request, "signup.html", {"departments": departments})

        if len(password) < 8:
            messages.error(request, "Password must be at least 8 characters long.")
            return render(request, "signup.html", {"departments": departments})

        if password != password2:
            messages.error(request, "Passwords do not match.")
            return render(request, "signup.html", {"departments": departments})

        roles = ["Intern", "Employee", "Supervisor"]
        
        if role not in roles:
            messages.error(request, "Choose a valid  selected.")
            return render(request, "signup.html", {"departments": departments})

        if User.objects.filter(email__iexact=email).exists():
            messages.error(request, "Email is already taken.")
            return render(request, "signup.html", {"departments": departments})

        try:
            with transaction.atomic():
                user = User.objects.create(
                    fullName=fullName,
                    email=email,
                    role=role,
                    department=department_obj.name,
                    password=make_password(password),
                )
                AuditLog.objects.create(
                    actor=user,
                    action="Member signed up",
                    target=f"{user.fullName} ({user.email}) - {user.role}",
                )
        except IntegrityError:
            messages.error(request, "Email is already taken.")
            return render(request, "signup.html", {"departments": departments})
        return redirect("/")
    return render(request, "signup.html", {"departments": departments})