from datetime import date, datetime, time, timedelta

from django.utils import timezone

LATE_GRACE_MINUTES = 30
ABSENCE_GRACE_MINUTES = 59


def local_datetime(day: date, clock_time: time) -> datetime:
    return timezone.make_aware(
        datetime.combine(day, clock_time),
        timezone.get_current_timezone(),
    )


def attendance_deadlines(
    check_in_time: time,
    day: date | None = None,
) -> tuple[datetime, datetime]:
    attendance_day = day or timezone.localdate()
    shift_start = local_datetime(attendance_day, check_in_time)
    return (
        shift_start + timedelta(minutes=LATE_GRACE_MINUTES),
        shift_start + timedelta(minutes=ABSENCE_GRACE_MINUTES),
    )
