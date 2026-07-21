"""Date utilities for the reporting period."""

from __future__ import annotations

from datetime import date, timedelta


def current_month_until_yesterday(today: date | None = None) -> tuple[date, date]:
    """Return the reporting month through yesterday.

    On the first day of a month there are no completed days in the current
    month, so the previous calendar month is returned in full.
    """
    today = today or date.today()
    end_date = today - timedelta(days=1)
    start_date = end_date.replace(day=1) if today.day == 1 else today.replace(day=1)
    return start_date, end_date
