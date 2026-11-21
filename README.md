# ERP System

A role-based ERP web application built with **Django** and **PostgreSQL**. It manages users, departments, attendance, tasks, leave requests, reports, notifications and organization settings from one platform.

## Features

| Module | What it does |
| --- | --- |
| Dashboards | A separate dashboard for each role, showing activity, attendance, pending tasks and key statistics. |
| User & role management | Self-signup with admin approval, admin-created users, role changes, password resets and profile pictures stored in the database. |
| Departments | Admins create and update departments; users belong to a department. |
| Attendance | Daily check-in and check-out, late detection against the organization's working hours, and attendance history. |
| Task management | Supervisors assign tasks with a deadline and priority; employees start tasks and submit work; supervisors approve or request revisions. |
| Leave management | Employees/Interns request leave (annual, sick, casual); HR approves or rejects. |
| Reports | HR exports CSV reports: monthly attendance, lateness, leave balances, task summary, intern roster and user roster. |
| Notifications & settings | In-app notifications, an audit log of key actions, and organization settings (name, check-in and check-out times). |

## Roles

| Role | Access |
| --- | --- |
| **Admin** | Full access: users, roles, approvals, departments and settings. Also gets access to the Django admin site at `/admin/`. |
| **HR** | Employee and intern records, attendance, leave requests, mentor assignment and HR reports. |
| **Supervisor** | Assign tasks, set deadlines, review submissions and monitor assigned team members. |
| **Employee / Intern** | Personal dashboard, check in and out, tasks and submissions, leave requests. |

Role access is enforced on the server for every page and action. A user without the right role is redirected to the Access Denied page.

## Tech stack

- Python 3.11 or newer
- Django 5.2
- PostgreSQL (driver: `psycopg2-binary`)
- HTML, CSS and vanilla JavaScript (no build step)

## Getting started

### 1. Prerequisites

- [Python 3.11+](https://www.python.org/downloads/)
- [PostgreSQL](https://www.postgresql.org/download/) running locally on port `5432`

### 2. Get the code and create a virtual environment

```powershell
cd path\to\epr
python -m venv venv
venv\Scripts\activate
```

On macOS or Linux, activate with `source venv/bin/activate` instead.

### 3. Install dependencies

```bash
pip install "Django>=5.2,<5.3" psycopg2-binary
```

### 4. Create the database

Open `psql` (or pgAdmin) and run:

```sql
CREATE DATABASE epr;
```

### 5. Configure the database connection

Open `epr/settings.py` and set the `DATABASES` block to match your PostgreSQL install:

```python
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'epr',
        'USER': 'postgres',
        'PASSWORD': 'your-postgres-password',
        'HOST': 'localhost',
        'PORT': '5432',
    }
}
```

### 6. Create the tables

```bash
python manage.py makemigrations
python manage.py migrate
```

This creates every table and seeds the default departments and the default organization settings (check-in 09:00, check-out 17:00).

### 7. Create the first Admin

```bash
python manage.py createsuperuser
```

Use an email address as the username or email. When this person logs in through the normal login page, the system automatically creates a matching **Admin** account and approves it.

### 8. Run the server

```bash
python manage.py runserver
```

Open <http://127.0.0.1:8000/> and log in with the superuser's email and password.

## How to use it

1. **Sign up:** new users register at `/signup/` as Intern, Employee or Supervisor. Their account stays pending until an Admin approves it. An admin can create a new admin both from the django admin panel and the custom admin dashboard but can only delete and admin from the django admin panel.
2. **Approve:** the Admin approves pending accounts from the custom Admin dashboard. Admins can also create users directly, change roles, reset passwords, manage departments and set working hours.
3. **Create HR users:** the HR role is assigned by an Admin (create the user or change an existing user's role).
4. **Assign mentors:** HR assigns each Employee or Intern to a Supervisor, who can then assign tasks to them.
5. **Day to day:** employees check in and out, work on tasks and request leave; supervisors review submissions; HR reviews leave and exports reports.

## Pages and routes

| URL | Purpose |
| --- | --- |
| `/` | Login |
| `/signup/` | Registration |
| `/epr/admin_dashboard/` | Admin dashboard |
| `/epr/hr/` | HR dashboard |
| `/epr/supervisor/` | Supervisor dashboard |
| `/epr/employee/` | Employee dashboard |
| `/epr/intern/` | Intern dashboard |
| `/epr/access-denied/` | Shown when a role is not allowed on a page |
| `/admin/` | Django admin site (Admin role only) |

## Database structure

PostgreSQL tables created by this project (Django's own `auth_*`, `django_*` and session tables are also created):

| Table | Key fields |
| --- | --- |
| `signup_user` | full name, email (unique), role, department, hashed password, is_approved, date_joined, mentor (self-reference) |
| `signup_profilepicture` | user (one-to-one), image (binary), content_type, updated_at |
| `admin_dashboard_department` | name (unique, case-insensitive), head, created_at |
| `admin_dashboard_organizationsettings` | organization name, check-in time, check-out time, updated_by, updated_at |
| `admin_dashboard_notification` | recipient, message, link, is_read, created_at |
| `admin_dashboard_auditlog` | actor, action, target, occurred_at |
| `employee_attendance` | employee, date, check_in, check_out, status (Present or Late); one row per employee per day |
| `employee_leaverequest` | employee, leave type, start and end date, reason, status (Pending, Approved, Rejected), reviewed_by, reviewed_at |
| `supervisor_task` | title, assigned_to, assigned_by, deadline, priority (low, medium, high), description, status |
| `supervisor_tasksubmission` | task, employee, notes, reference link, status (Submitted, Approved, Revision Requested), review note; one submission per task per employee |

The full schema is defined by the migration files in each app's `migrations/` folder, so `python manage.py migrate` recreates it on any empty database.

## Project structure

```
epr/                 Project settings, root URLs, WSGI/ASGI
home/                Login, logout, notifications, profile picture upload and serving
signup/              User model, profile picture model, registration
admin_dashboard/     Admin dashboard, departments, settings, audit log, notifications
hr/                  HR dashboard, mentor assignment, leave review, CSV reports
supervisor/          Task creation and submission review
employee/            Attendance, leave requests, task work, attendance policy
access_denied/       403 page for unauthorized access
templates/           HTML templates
static/              CSS and JavaScript
```

## Shipping checklist

**For the project submission**

- [ ] Include the full source code (all folders above plus `manage.py`).
- [ ] Do not include your virtual environment folder (`venv/`) or any `__pycache__/` folders.
- [ ] Replace your real database password in `epr/settings.py` with a placeholder before sharing the code.
- [ ] Keep this README so reviewers can follow the setup steps and the database structure above.

**Before putting it on a live server**

- [ ] Set `DEBUG = False` in `epr/settings.py`.
- [ ] Replace the `SECRET_KEY` with a new secret value and keep it out of the code (for example, read it from an environment variable).
- [ ] Set `ALLOWED_HOSTS` to your domain name(s).
- [ ] Use a strong PostgreSQL password and read it from an environment variable instead of writing it in the file.
- [ ] Run `python manage.py collectstatic` and serve the files from `staticfiles/` with your web server (or WhiteNoise).
- [ ] Run the app with a production server such as Gunicorn (Linux) or Waitress (Windows) behind HTTPS.
- [ ] Run `python manage.py migrate` on the production database.
