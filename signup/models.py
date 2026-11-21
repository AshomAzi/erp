from django.db import models

# Create your models here.

class User(models.Model):
    ROLE_CHOICES = [
        ('Admin', 'Admin'),
        ('HR', 'HR'),
        ('Intern', 'Intern'),
        ('Employee', 'Employee'),
        ('Supervisor', 'Supervisor'),
    ]

    DEPARTMENT_CHOICES = [
        ('Software Engineering', 'Software Engineering'),
        ('IT Support & Service Desk', 'IT Support & Service Desk'),
        ('Cyber Security', 'Cyber Security'),
        ('Data Science & Analytics', 'Data Science & Analytics'),
        ('Cloud & Infrastructure', 'Cloud & Infrastructure'),
        ('Product Management', 'Product Management'),
    ]

    fullName = models.CharField(max_length=100)
    email = models.EmailField(unique=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    department = models.CharField(max_length=50, choices=DEPARTMENT_CHOICES)
    password = models.CharField(max_length=128)
    date_joined = models.DateField(auto_now_add=True, null=True, blank=True)
    is_approved = models.BooleanField(default=False)
    mentor = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="mentees",
    )

    def __str__(self):
        return self.email