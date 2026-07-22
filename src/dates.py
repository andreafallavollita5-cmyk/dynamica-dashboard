"""Date utilities for the reporting period."""

from __future__ import annotations

from datetime import date, timedelta


def weekdays_inclusive(start_date: date, end_date: date) -> int:
    """Count Monday-Friday dates in an inclusive interval."""
    if end_date < start_date:
        return 0
    return sum(
        1
        for offset in range((end_date - start_date).days + 1)
        if (start_date + timedelta(days=offset)).weekday() < 5
    )


def weekdays_in_month(value: date) -> int:
    """Count Monday-Friday dates in the calendar month containing ``value``."""
    next_month = (
        value.replace(year=value.year + 1, month=1, day=1)
        if value.month == 12
        else value.replace(month=value.month + 1, day=1)
    )
    return weekdays_inclusive(value.replace(day=1), next_month - timedelta(days=1))


def current_month_until_yesterday(today: date | None = None) -> tuple[date, date]:
    """Return the reporting month through yesterday.

    On the first day of a month there are no completed days in the current
    month, so the previous calendar month is returned in full.
    """
    today = today or date.today()
    end_date = today - timedelta(days=1)
    start_date = end_date.replace(day=1) if today.day == 1 else today.replace(day=1)
    return start_date, end_date
