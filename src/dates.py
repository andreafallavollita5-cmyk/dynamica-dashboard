"""Date utilities for the reporting period."""

from __future__ import annotations

from datetime import date, timedelta


def current_month_until_yesterday(today: date | None = None) -> tuple[date, date]:
    """Return first day of current month and yesterday."""
    today = today or date.today()
    start_date = today.replace(day=1)
    end_date = today - timedelta(days=1)
    return start_date, end_date
