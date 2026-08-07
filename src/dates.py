"""Date utilities for the reporting period."""

from __future__ import annotations

from datetime import date, timedelta


def easter_sunday(year: int) -> date:
    """Return Gregorian Easter Sunday for ``year``."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    month_adjustment = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * month_adjustment) // 451
    month = (h + month_adjustment - 7 * m + 114) // 31
    day = (h + month_adjustment - 7 * m + 114) % 31 + 1
    return date(year, month, day)


def italian_public_holidays(year: int) -> frozenset[date]:
    """Return Italian nationwide public holidays for ``year``."""
    fixed = (
        (1, 1), (1, 6), (4, 25), (5, 1), (6, 2), (8, 15),
        (11, 1), (12, 8), (12, 25), (12, 26),
    )
    return frozenset(
        {date(year, month, day) for month, day in fixed}
        | {easter_sunday(year) + timedelta(days=1)}
    )


def working_days_inclusive(start_date: date, end_date: date) -> int:
    """Count Mon-Fri dates excluding Italian nationwide public holidays."""
    if end_date < start_date:
        return 0
    holidays = set()
    for year in range(start_date.year, end_date.year + 1):
        holidays.update(italian_public_holidays(year))
    return sum(
        1
        for offset in range((end_date - start_date).days + 1)
        if (current := start_date + timedelta(days=offset)).weekday() < 5
        and current not in holidays
    )


def working_days_in_month(value: date) -> int:
    """Count working days in the month, excluding Italian public holidays."""
    next_month = (
        value.replace(year=value.year + 1, month=1, day=1)
        if value.month == 12
        else value.replace(month=value.month + 1, day=1)
    )
    return working_days_inclusive(
        value.replace(day=1), next_month - timedelta(days=1)
    )


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
