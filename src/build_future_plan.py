"""Build a published plan-only dashboard dataset for one calendar month."""

from __future__ import annotations

import argparse
import calendar
import json
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from src.build_daily_metrics import DAILY_METRIC_COLUMNS
from src.build_report_data import (
    REPORT_COLUMNS,
    _append_official_rows,
    _write_csv,
    build_report_rows,
)
from src.config import load_settings
from src.dates import working_days_inclusive, working_days_in_month
from src.google_sheets_client import (
    fetch_manual_inputs,
    monthly_manual_worksheet_name,
)


ROOT = Path(__file__).resolve().parents[1]
PLANS_ROOT = ROOT / "data" / "plans"
ACTUAL_FIELDS = (
    "lead_effettive",
    "delta_lead",
    "speso_effettivo",
    "delta_speso",
    "delta_delivery_pct",
    "cpl_effettivo",
    "delta_cpl",
)


def parse_month(value: str) -> date:
    try:
        parsed = datetime.strptime(value, "%Y-%m").date()
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Il mese deve avere formato YYYY-MM.") from exc
    return parsed.replace(day=1)


def build_future_plan_rows(manual_rows: list[dict], month_start: date) -> list[dict]:
    """Return campaign and summary rows with planning metrics and no actuals."""
    month_end = month_start.replace(
        day=calendar.monthrange(month_start.year, month_start.month)[1]
    )
    campaign_rows = build_report_rows(
        manual_rows,
        google_rows=[],
        meta_rows=[],
        microsoft_rows=[],
        start_date=month_start,
        end_date=month_end,
        google_status="ok",
        meta_status="ok",
        microsoft_status="ok",
        report_date=date.today(),
    )
    for row in campaign_rows:
        for field in ACTUAL_FIELDS:
            row[field] = None
        row["source_status"] = "plan:future"
        row["lead_allocation_method"] = ""

    rows = _append_official_rows(
        campaign_rows,
        manual_rows=manual_rows,
        days_in_month=calendar.monthrange(month_start.year, month_start.month)[1],
        elapsed_days=(month_end - month_start).days + 1,
        dem_days_in_month=working_days_in_month(month_start),
        dem_elapsed_days=working_days_inclusive(month_start, month_end),
        area_clienti_total=None,
    )
    for row in rows:
        for field in ACTUAL_FIELDS:
            row[field] = None
        row["source_status"] = "plan:future"
        row["lead_allocation_method"] = ""
    return rows


def build_future_plan(
    month_start: date,
    output_root: Path = PLANS_ROOT,
    manual_fetcher=None,
) -> Path:
    """Generate the plan-only files consumed by the dashboard."""
    if month_start.day != 1:
        month_start = month_start.replace(day=1)
    month_end = month_start.replace(
        day=calendar.monthrange(month_start.year, month_start.month)[1]
    )
    manual_rows = (
        manual_fetcher()
        if manual_fetcher is not None
        else fetch_manual_inputs(month_start)
    )
    rows = build_future_plan_rows(manual_rows, month_start)
    destination = output_root / month_start.strftime("%Y-%m")
    destination.mkdir(parents=True, exist_ok=True)
    _write_csv(destination / "report_data.csv", rows, REPORT_COLUMNS)
    _write_csv(
        destination / "report_daily_metrics.csv", [], list(DAILY_METRIC_COLUMNS)
    )
    settings = load_settings()
    metadata = {
        "client": settings.client_name,
        "start_date": month_start.isoformat(),
        "end_date": month_end.isoformat(),
        "updated_at": datetime.now(ZoneInfo(settings.timezone)).isoformat(),
        "status": "planned",
        "dataset_type": "future_plan",
        "actuals_available": False,
        "source_worksheet": monthly_manual_worksheet_name(month_start),
    }
    (destination / "last_update.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return destination


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--month", required=True, type=parse_month)
    parser.add_argument("--output-root", type=Path, default=PLANS_ROOT)
    args = parser.parse_args(argv)
    try:
        destination = build_future_plan(args.month, args.output_root)
    except Exception as exc:
        print(f"Errore generazione piano futuro: {exc}")
        return 1
    print(f"Piano futuro generato: {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
