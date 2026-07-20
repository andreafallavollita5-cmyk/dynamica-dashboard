"""Build privacy-safe daily campaign metrics for the published dashboard."""

from __future__ import annotations

import argparse
import os
from datetime import date
from pathlib import Path

import pandas as pd

from src.crm_excel_client import read_crm_export
from src.crm_lead_matcher import match_crm_leads
from src.google_sheets_client import (
    fetch_crm_mapping_from_google_sheet,
    fetch_manual_inputs,
)


ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = ROOT / "data" / "report_data.csv"
SPEND_PATH = ROOT / "data" / "report_daily.csv"
OUTPUT_PATH = ROOT / "data" / "report_daily_metrics.csv"
DAILY_METRIC_COLUMNS = (
    "date",
    "source",
    "excel_row",
    "spend_rollup_excel_row",
    "campaign_id",
    "campaign_name",
    "spend",
    "leads",
    "monthly_lead_target",
    "lead_allocation_method",
)


class DailyMetricsError(RuntimeError):
    """Raised when daily aggregates cannot be built safely."""


def _clean_id(value: object) -> str:
    text = "" if pd.isna(value) else str(value).strip()
    return text[:-2] if text.endswith(".0") else text


def build_daily_metric_rows(
    report: pd.DataFrame,
    spend: pd.DataFrame,
    normalized_leads: list[dict],
    planning_targets: dict[str, float] | None = None,
) -> list[dict]:
    """Return aggregate rows without lead IDs or other CRM personal data."""
    campaign_rows = report[report["row_type"].fillna("campaign") == "campaign"].copy()
    if campaign_rows.empty:
        raise DailyMetricsError("Il report non contiene righe campagna.")
    start = pd.to_datetime(report["start_date"], errors="raise").dt.date.unique()
    end = pd.to_datetime(report["end_date"], errors="raise").dt.date.unique()
    if len(start) != 1 or len(end) != 1:
        raise DailyMetricsError("Il report contiene più periodi.")

    rows: list[dict] = []
    campaign_rows["excel_row"] = pd.to_numeric(
        campaign_rows["excel_row"], errors="coerce"
    )
    campaign_rows = campaign_rows.sort_values("excel_row")
    spend_targets: dict[tuple[str, str], tuple[int, int]] = {}
    previous_row: int | None = None
    for item in campaign_rows.to_dict("records"):
        excel_row = int(item["excel_row"])
        platform = str(item.get("platform") or "").casefold()
        source = "google_ads" if "google" in platform else "meta_ads" if "meta" in platform else ""
        campaign_id = _clean_id(
            item.get("google_campaign_id") or item.get("meta_campaign_id")
        )
        target_row = excel_row
        is_continuation = (
            campaign_id
            and not str(item.get("investimento_media") or "").strip()
            and "quinto digitale" in str(item.get("campaign_name") or "").casefold()
            and previous_row is not None
        )
        if is_continuation:
            target_row = previous_row
        if source and campaign_id:
            spend_targets[(source, campaign_id)] = (excel_row, target_row)
        previous_row = excel_row
    if not spend.empty:
        required = {"date", "source", "campaign_id", "campaign_name", "spend"}
        missing = sorted(required - set(spend.columns))
        if missing:
            raise DailyMetricsError(
                "Colonne spesa giornaliera mancanti: " + ", ".join(missing)
            )
        spend = spend.copy()
        spend["date"] = pd.to_datetime(spend["date"], errors="raise").dt.date
        spend = spend[(spend["date"] >= start[0]) & (spend["date"] <= end[0])]
        for item in spend.to_dict("records"):
            source = str(item.get("source") or "")
            campaign_id = _clean_id(item.get("campaign_id"))
            source_row, target_row = spend_targets.get(
                (source, campaign_id), ("", "")
            )
            rows.append(
                {
                    "date": item["date"].isoformat(),
                    "source": source,
                    "excel_row": source_row,
                    "spend_rollup_excel_row": target_row,
                    "campaign_id": campaign_id,
                    "campaign_name": str(item.get("campaign_name") or ""),
                    "spend": float(item.get("spend") or 0),
                    "leads": "",
                    "monthly_lead_target": "",
                    "lead_allocation_method": "",
                }
            )

    normal_counts: dict[tuple[str, int], int] = {}
    area_counts: dict[str, int] = {}
    for lead in normalized_leads:
        if str(lead.get("match_status") or "") != "matched":
            continue
        created = pd.Timestamp(lead["created_at"]).date().isoformat()
        method = str(lead.get("lead_allocation_method") or "")
        if method == "area_clienti_uniform":
            area_counts[created] = area_counts.get(created, 0) + 1
            continue
        excel_row = int(lead["matched_excel_row"])
        key = (created, excel_row)
        normal_counts[key] = normal_counts.get(key, 0) + 1

    names_by_row = {
        int(row.excel_row): str(row.campaign_name)
        for row in campaign_rows.itertuples()
        if not pd.isna(row.excel_row)
    }
    for (created, excel_row), count in sorted(normal_counts.items()):
        rows.append(
            {
                "date": created,
                    "source": "crm",
                    "excel_row": excel_row,
                    "spend_rollup_excel_row": "",
                "campaign_id": "",
                "campaign_name": names_by_row.get(excel_row, ""),
                "spend": "",
                    "leads": count,
                    "monthly_lead_target": "",
                    "lead_allocation_method": "crm_mapping",
            }
        )
    for created, count in sorted(area_counts.items()):
        rows.append(
            {
                "date": created,
                "source": "crm_area_clienti",
                "excel_row": "",
                "spend_rollup_excel_row": "",
                "campaign_id": "",
                "campaign_name": "AREA CLIENTI",
                "spend": "",
                "leads": count,
                "monthly_lead_target": "",
                "lead_allocation_method": "area_clienti_uniform",
            }
        )
    for label, target in sorted((planning_targets or {}).items()):
        rows.append(
            {
                "date": start[0].isoformat(),
                "source": "planning",
                "excel_row": "",
                "spend_rollup_excel_row": "",
                "campaign_id": "",
                "campaign_name": label,
                "spend": "",
                "leads": "",
                "monthly_lead_target": target,
                "lead_allocation_method": "",
            }
        )

    source_order = {
        "planning": 0, "google_ads": 1, "meta_ads": 2,
        "crm": 3, "crm_area_clienti": 4,
    }
    return sorted(
        rows,
        key=lambda row: (
            str(row["date"]),
            source_order.get(str(row["source"]), 9),
            str(row["excel_row"]),
            str(row["campaign_id"]),
        ),
    )


def build_daily_metrics(
    report_path: Path = REPORT_PATH,
    spend_path: Path = SPEND_PATH,
    output_path: Path = OUTPUT_PATH,
    crm_export_path: str | Path | None = None,
    mapping_fetcher=fetch_crm_mapping_from_google_sheet,
    manual_fetcher=fetch_manual_inputs,
) -> Path:
    report = pd.read_csv(report_path, dtype=str, keep_default_na=False)
    spend = (
        pd.read_csv(spend_path, dtype={"campaign_id": str}, keep_default_na=False)
        if spend_path.exists()
        else pd.DataFrame()
    )
    starts = pd.to_datetime(report["start_date"], errors="raise").dt.date.unique()
    ends = pd.to_datetime(report["end_date"], errors="raise").dt.date.unique()
    if len(starts) != 1 or len(ends) != 1:
        raise DailyMetricsError("Periodo report non univoco.")
    crm_path = Path(
        crm_export_path
        or os.getenv("CRM_EXPORT_PATH", "").strip()
        or ROOT / "data/input/LEAD QUESTO MESE PULITE 18-07-2026 11-09-08.xlsx"
    )
    if not crm_path.is_absolute():
        crm_path = ROOT / crm_path
    leads = read_crm_export(crm_path, starts[0], ends[0])
    manual_rows = manual_fetcher()
    _allocations, _methods, normalized = match_crm_leads(
        leads, manual_rows, mapping_fetcher()
    )
    planning_targets: dict[str, float] = {}
    if manual_rows:
        first = manual_rows[0]
        for slug, label in (
            ("area_clienti", "TOT Area Clienti"),
            ("lead_veloce", "TOT Lead Veloce"),
            ("dem", "TOT DEM"),
        ):
            value = first.get(f"sheet_{slug}_stima_lead_subtotal")
            if isinstance(value, (int, float)):
                planning_targets[label] = float(value)
    rows = build_daily_metric_rows(
        report, spend, normalized, planning_targets=planning_targets
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows, columns=DAILY_METRIC_COLUMNS).to_csv(
        output_path, index=False, encoding="utf-8-sig"
    )
    return output_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--crm-export", type=Path)
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    args = parser.parse_args()
    try:
        path = build_daily_metrics(
            output_path=args.output, crm_export_path=args.crm_export
        )
    except Exception as exc:
        print(f"Errore metriche giornaliere: {exc}")
        return 1
    print(f"Metriche giornaliere generate: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
