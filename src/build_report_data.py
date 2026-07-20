"""Build the final ``data/report_data.csv`` from manual and Ads API data."""

from __future__ import annotations

import argparse
import calendar
import csv
import json
import math
import os
from collections.abc import Callable
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from src.ads_verification import fetch_delivery_with_status
from src.config import load_settings
from src.crm_excel_client import read_crm_export
from src.crm_lead_matcher import match_crm_leads
from src.dates import current_month_until_yesterday
from src.google_ads_client import fetch_google_campaign_delivery
from src.google_sheets_client import (
    fetch_crm_mapping_from_google_sheet,
    fetch_manual_inputs,
)
from src.meta_ads_client import fetch_meta_campaign_delivery
from src.report_groups import CLIENT_GROUPS, SUMMARY_FIELDS, client_subtotal_group
from src.utils import safe_divide


ROOT = Path(__file__).resolve().parents[1]
REPORT_COLUMNS = [
    "row_type", "report_date", "start_date", "end_date", "excel_row", "funnel",
    "platform", "channel", "campaign_name", "investimento_media",
    "percentuale_investimento", "cpp_medio", "stima_pratiche", "cpl_target",
    "stima_lead", "stima_lead_giornaliere", "stima_lead_progressiva",
    "lead_effettive", "delta_lead", "stima_spending_progressiva",
    "speso_effettivo", "delta_speso", "delta_delivery_pct", "cpl_effettivo",
    "delta_cpl", "action", "google_campaign_id", "meta_campaign_id",
    "dynamics_campaign_key", "source_status", "lead_allocation_method",
]
DELIVERY_COLUMNS = [
    "platform", "campaign_id", "campaign_name", "start_date", "end_date",
    "spend", "clicks", "impressions",
]

ManualFetcher = Callable[[], list[dict]]
DeliveryFetcher = Callable[[str, str], list[dict]]
MappingFetcher = Callable[[], list[dict]]


def _number(value: object) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _sheet_value_or(manual: dict, key: str, fallback: float | None) -> float | None:
    """Prefer an evaluated legacy-Sheet value when that column is present."""
    return _number(manual.get(key)) if key in manual else fallback


MANUAL_SUMMARY_FIELDS = (
    "investimento_media",
    "percentuale_investimento",
    "cpp_medio",
    "stima_pratiche",
    "cpl_target",
    "stima_lead",
    "stima_lead_giornaliere",
    "stima_lead_progressiva",
    "lead_effettive",
    "stima_spending_giornaliera",
    "stima_spending_progressiva",
)


def _official_summary_values(
    official: dict,
    source_prefix: str,
    source_suffix: str,
    spend: float | None,
) -> dict[str, float | None]:
    """Build one upstream summary from manual official fields and current spend."""
    values = {
        field: _number(official.get(f"{source_prefix}{field}{source_suffix}"))
        for field in MANUAL_SUMMARY_FIELDS
    }
    values["speso_effettivo"] = spend
    lead = values["lead_effettive"]
    lead_plan = values["stima_lead_progressiva"]
    spend_plan = values["stima_spending_progressiva"]
    cpl_target = values["cpl_target"]
    values["delta_lead"] = (
        lead - lead_plan if lead is not None and lead_plan is not None else None
    )
    values["delta_speso"] = (
        spend - spend_plan if spend is not None and spend_plan is not None else None
    )
    values["delta_delivery_pct"] = safe_divide(values["delta_speso"], spend_plan)
    values["cpl_effettivo"] = safe_divide(spend, lead)
    values["delta_cpl"] = (
        values["cpl_effettivo"] - cpl_target
        if values["cpl_effettivo"] is not None and cpl_target is not None
        else None
    )
    return values


def build_official_summaries(
    manual_rows: list[dict], output_rows: list[dict]
) -> dict[str, float | None]:
    """Return official total/subtotal fields to duplicate on the final DataFrame."""
    if not manual_rows or not output_rows:
        return {}
    official = manual_rows[0]
    spend_values = [_number(row.get("speso_effettivo")) for row in output_rows]
    total_spend = (
        sum(value or 0 for value in spend_values)
        if any(value is not None for value in spend_values)
        else None
    )
    total = _official_summary_values(official, "sheet_total_", "", total_spend)
    summaries = {
        f"kpi_{field}_totale": total.get(field) for field in SUMMARY_FIELDS
    }

    for slug, _label in CLIENT_GROUPS:
        group_rows = [
            row for row in output_rows if client_subtotal_group(row) == slug
        ]
        group_spends = [_number(row.get("speso_effettivo")) for row in group_rows]
        group_spend = (
            sum(value or 0 for value in group_spends)
            if any(value is not None for value in group_spends)
            else None
        )
        subtotal = _official_summary_values(
            official, f"sheet_{slug}_", "_subtotal", group_spend
        )
        summaries.update(
            {
                f"subtotal_{slug}_{field}": subtotal.get(field)
                for field in SUMMARY_FIELDS
            }
        )
    return summaries


def _index_delivery(rows: list[dict]) -> tuple[dict[str, dict], dict[str, list[dict]]]:
    by_id: dict[str, dict] = {}
    by_name: dict[str, list[dict]] = {}
    for row in rows:
        campaign_id = str(row.get("campaign_id") or "").strip()
        campaign_name = str(row.get("campaign_name") or "").strip()
        if campaign_id:
            by_id[campaign_id] = row
        if campaign_name:
            by_name.setdefault(campaign_name.casefold(), []).append(row)
    return by_id, by_name


def _match_spend(
    manual: dict,
    api_rows: list[dict],
    id_column: str,
    platform_key: str,
    connection_status: str,
) -> tuple[float | None, str]:
    if connection_status != "ok":
        return None, f"{platform_key}:error"

    by_id, by_name = _index_delivery(api_rows)
    campaign_id = str(manual.get(id_column) or "").strip()
    if campaign_id:
        match = by_id.get(campaign_id)
        if match is None:
            return 0.0, f"{platform_key}:no_delivery"
        return float(match.get("spend") or 0), f"{platform_key}:ok"

    campaign_name = str(manual.get("campaign_name") or "").strip()
    name_matches = by_name.get(campaign_name.casefold(), [])
    if len(name_matches) == 1:
        return float(name_matches[0].get("spend") or 0), f"{platform_key}:ok_name_fallback"
    if len(name_matches) > 1:
        return None, f"{platform_key}:ambiguous_name"
    return 0.0, f"{platform_key}:no_delivery_name"


def _platforms_for_row(row: dict) -> list[tuple[str, str]]:
    platforms: list[tuple[str, str]] = []
    if str(row.get("google_campaign_id") or "").strip():
        platforms.append(("google", "google_campaign_id"))
    if str(row.get("meta_campaign_id") or "").strip():
        platforms.append(("meta", "meta_campaign_id"))
    if platforms:
        return platforms

    platform = str(row.get("platform") or "").casefold()
    if "google" in platform:
        return [("google", "google_campaign_id")]
    if "meta" in platform or "facebook" in platform or "instagram" in platform:
        return [("meta", "meta_campaign_id")]
    return []


def _resolve_ads_spend(
    manual_rows: list[dict],
    delivery: dict[str, list[dict]],
    statuses: dict[str, str],
) -> tuple[list[float | None], list[list[str]], list[bool]]:
    """Match Ads spend and preserve legacy continuation-row rollups.

    In the visual agency sheet, a campaign row with an Ads ID but no budget is
    a continuation of the preceding budgeted row in the same funnel/platform/
    channel. Its API spend belongs to that parent row, as in the Excel template.
    """
    spends: list[float | None] = []
    sources: list[list[str]] = []
    failures: list[bool] = []
    platforms_by_row: list[list[tuple[str, str]]] = []

    for manual in manual_rows:
        spend_parts: list[float] = []
        source_parts: list[str] = []
        platforms = _platforms_for_row(manual)
        platforms_by_row.append(platforms)
        for platform_key, id_column in platforms:
            spend, source = _match_spend(
                manual,
                delivery[platform_key],
                id_column,
                platform_key,
                statuses[platform_key],
            )
            source_parts.append(source)
            if spend is not None:
                spend_parts.append(spend)
        failed = any(statuses[key] != "ok" for key, _ in platforms)
        failures.append(failed)
        spends.append(None if failed else (sum(spend_parts) if platforms else None))
        sources.append(source_parts)

    last_parent: dict[tuple[str, str, str], int] = {}
    for index, manual in enumerate(manual_rows):
        group = tuple(
            str(manual.get(key) or "").strip().casefold()
            for key in ("funnel", "platform", "channel")
        )
        if _number(manual.get("investimento_media")) is not None:
            last_parent[group] = index
            continue
        has_explicit_ads_id = bool(
            str(manual.get("google_campaign_id") or "").strip()
            or str(manual.get("meta_campaign_id") or "").strip()
        )
        if not has_explicit_ads_id or not platforms_by_row[index] or group not in last_parent:
            continue

        parent = last_parent[group]
        if failures[index] or failures[parent]:
            continue
        child_spend = spends[index]
        if child_spend is not None:
            spends[parent] = (spends[parent] or 0) + child_spend
        platform_key = platforms_by_row[index][0][0]
        child_row = manual.get("excel_row")
        parent_row = manual_rows[parent].get("excel_row")
        sources[parent].append(f"{platform_key}:includes_excel_row_{child_row}")
        sources[index] = [f"{platform_key}:rolled_up_to_excel_row_{parent_row}"]
        spends[index] = None

    return spends, sources, failures


def build_report_rows(
    manual_rows: list[dict],
    google_rows: list[dict],
    meta_rows: list[dict],
    start_date: date,
    end_date: date,
    google_status: str = "ok",
    meta_status: str = "ok",
    report_date: date | None = None,
    crm_leads_by_excel_row: dict[int, int] | None = None,
    lead_allocation_methods: dict[int, str] | None = None,
) -> list[dict]:
    """Pure merge/calculation function, kept injectable for technical mocks."""
    report_date = report_date or date.today()
    days_in_month = calendar.monthrange(start_date.year, start_date.month)[1]
    elapsed_days = max((end_date - start_date).days + 1, 0)
    delivery = {"google": google_rows, "meta": meta_rows}
    statuses = {"google": google_status, "meta": meta_status}
    output: list[dict] = []
    crm_mode = crm_leads_by_excel_row is not None
    crm_leads_by_excel_row = crm_leads_by_excel_row or {}
    lead_allocation_methods = lead_allocation_methods or {}
    ads_spends, ads_sources, connection_failures = _resolve_ads_spend(
        manual_rows, delivery, statuses
    )

    for index, manual in enumerate(manual_rows):
        source_parts = ads_sources[index]
        platforms = _platforms_for_row(manual)
        investimento = _number(manual.get("investimento_media"))
        stima_lead = _number(manual.get("stima_lead"))
        excel_row = int(manual.get("excel_row") or 0)
        lead_effettive = (
            float(crm_leads_by_excel_row.get(excel_row, 0))
            if crm_mode
            else _number(manual.get("lead_effettive_manual"))
        )
        cpl_target = _number(manual.get("cpl_target"))

        if connection_failures[index]:
            speso_effettivo = None
        elif platforms:
            speso_effettivo = ads_spends[index]
        else:
            if crm_mode:
                is_dem = client_subtotal_group(manual) == "dem"
                speso_effettivo = (
                    lead_effettive * cpl_target
                    if is_dem and cpl_target is not None
                    else None
                )
            else:
                speso_effettivo = _number(manual.get("speso_effettivo_manual"))
                if speso_effettivo is not None:
                    source_parts.append("manual:sheet_spend")

        calculated_lead_giornaliere = safe_divide(stima_lead, days_in_month)
        stima_lead_giornaliere = (
            calculated_lead_giornaliere
            if crm_mode
            else _sheet_value_or(
                manual, "stima_lead_giornaliere", calculated_lead_giornaliere
            )
        )
        calculated_lead_progressiva = (
            stima_lead_giornaliere * elapsed_days
            if stima_lead_giornaliere is not None else None
        )
        stima_lead_progressiva = (
            calculated_lead_progressiva
            if crm_mode
            else _sheet_value_or(
                manual, "stima_lead_progressiva", calculated_lead_progressiva
            )
        )
        calculated_spending_progressiva = (
            investimento / days_in_month * elapsed_days
            if investimento is not None else None
        )
        stima_spending_progressiva = (
            calculated_spending_progressiva
            if crm_mode
            else _sheet_value_or(
                manual, "stima_spending_progressiva", calculated_spending_progressiva
            )
        )
        calculated_delta_lead = (
            lead_effettive - stima_lead_progressiva
            if lead_effettive is not None and stima_lead_progressiva is not None else None
        )
        delta_lead = (
            calculated_delta_lead
            if crm_mode
            else _sheet_value_or(manual, "delta_lead", calculated_delta_lead)
        )
        delta_speso = (
            speso_effettivo - stima_spending_progressiva
            if speso_effettivo is not None and stima_spending_progressiva is not None else None
        )
        delta_delivery_pct = safe_divide(delta_speso, stima_spending_progressiva)
        cpl_effettivo = safe_divide(speso_effettivo, lead_effettive)
        delta_cpl = (
            cpl_effettivo - cpl_target
            if cpl_effettivo is not None and cpl_target is not None else None
        )

        output.append(
            {
                "row_type": "campaign",
                "report_date": report_date.isoformat(),
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "excel_row": excel_row,
                "funnel": manual.get("funnel"),
                "platform": manual.get("platform"),
                "channel": manual.get("channel"),
                "campaign_name": manual.get("campaign_name"),
                "investimento_media": investimento,
                "percentuale_investimento": _number(manual.get("percentuale_investimento")),
                "cpp_medio": _number(manual.get("cpp_medio")),
                "stima_pratiche": _number(manual.get("stima_pratiche")),
                "cpl_target": cpl_target,
                "stima_lead": stima_lead,
                "stima_lead_giornaliere": stima_lead_giornaliere,
                "stima_lead_progressiva": stima_lead_progressiva,
                "lead_effettive": lead_effettive,
                "delta_lead": delta_lead,
                "stima_spending_progressiva": stima_spending_progressiva,
                "speso_effettivo": speso_effettivo,
                "delta_speso": delta_speso,
                "delta_delivery_pct": delta_delivery_pct,
                "cpl_effettivo": cpl_effettivo,
                "delta_cpl": delta_cpl,
                "action": manual.get("action"),
                "google_campaign_id": str(manual.get("google_campaign_id") or ""),
                "meta_campaign_id": str(manual.get("meta_campaign_id") or ""),
                "dynamics_campaign_key": str(manual.get("dynamics_campaign_key") or ""),
                "source_status": (
                    (
                        "error"
                        if connection_failures[index]
                        else "manual"
                        if (
                            client_subtotal_group(manual) == "dem"
                            or lead_allocation_methods.get(excel_row)
                            == "area_clienti_uniform"
                        )
                        else "success"
                    )
                    if crm_mode
                    else ";".join(source_parts) if source_parts else "manual:no_ads_source"
                ),
                "lead_allocation_method": lead_allocation_methods.get(
                    excel_row, "crm_mapping"
                ),
            }
        )
    if not output:
        return output
    if crm_mode:
        return _append_official_rows(output)

    totals = {
        **build_official_summaries(manual_rows, output),
        "sheet_area_clienti_lead_effettive_subtotal": _number(
            manual_rows[0].get("sheet_area_clienti_lead_effettive_subtotal")
        ),
        "sheet_area_clienti_stima_lead_progressiva_subtotal": _number(
            manual_rows[0].get("sheet_area_clienti_stima_lead_progressiva_subtotal")
        ),
    }
    for row in output:
        row.update(totals)
    return output


def _sum(rows: list[dict], field: str) -> float | None:
    values = [_number(row.get(field)) for row in rows]
    return sum(value or 0 for value in values) if any(v is not None for v in values) else None


def _summary_row(rows: list[dict], label: str, row_type: str) -> dict:
    investment = _sum(rows, "investimento_media")
    practices = _sum(rows, "stima_pratiche")
    lead_target = _sum(rows, "stima_lead")
    lead_progress = _sum(rows, "stima_lead_progressiva")
    leads = _sum(rows, "lead_effettive")
    spend_plan = _sum(rows, "stima_spending_progressiva")
    spend = _sum(rows, "speso_effettivo")
    cpp = safe_divide(investment, practices)
    cpl_target = safe_divide(investment, lead_target)
    cpl = safe_divide(spend, leads)
    delta_lead = (
        leads - lead_progress if leads is not None and lead_progress is not None else None
    )
    delta_spend = (
        spend - spend_plan if spend is not None and spend_plan is not None else None
    )
    statuses = {str(row.get("source_status") or "") for row in rows}
    status = (
        "error"
        if "error" in statuses
        else "partial"
        if "partial" in statuses or len(statuses) > 1
        else "manual"
        if statuses == {"manual"}
        else "success"
    )
    first = rows[0]
    return {
        **{column: None for column in REPORT_COLUMNS},
        "row_type": row_type,
        "report_date": first.get("report_date"),
        "start_date": first.get("start_date"),
        "end_date": first.get("end_date"),
        "funnel": label,
        "campaign_name": label,
        "investimento_media": investment,
        "percentuale_investimento": _sum(rows, "percentuale_investimento"),
        "cpp_medio": cpp,
        "stima_pratiche": practices,
        "cpl_target": cpl_target,
        "stima_lead": lead_target,
        "stima_lead_giornaliere": _sum(rows, "stima_lead_giornaliere"),
        "stima_lead_progressiva": lead_progress,
        "lead_effettive": leads,
        "delta_lead": delta_lead,
        "stima_spending_progressiva": spend_plan,
        "speso_effettivo": spend,
        "delta_speso": delta_spend,
        "delta_delivery_pct": safe_divide(delta_spend, spend_plan),
        "cpl_effettivo": cpl,
        "delta_cpl": cpl - cpl_target if cpl is not None and cpl_target is not None else None,
        "source_status": status,
    }


def _append_official_rows(campaign_rows: list[dict]) -> list[dict]:
    output = list(campaign_rows)
    for slug, label in CLIENT_GROUPS:
        group = [row for row in campaign_rows if client_subtotal_group(row) == slug]
        if group:
            output.append(_summary_row(group, f"TOT {label}", "subtotal"))
    output.append(_summary_row(campaign_rows, "TOTALE GENERALE", "total"))
    return output


def _write_csv(path: Path, rows: list[dict], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def build_report_data(
    output_path: Path = Path("data/report_data.csv"),
    today: date | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    crm_export_path: str | Path | None = None,
    manual_fetcher: ManualFetcher | None = None,
    mapping_fetcher: MappingFetcher | None = None,
    google_fetcher: DeliveryFetcher | None = None,
    meta_fetcher: DeliveryFetcher | None = None,
) -> Path:
    """Run the read-only sources and generate CSV plus safe update metadata."""
    today = today or date.today()
    default_start, default_end = current_month_until_yesterday(today)
    start = start_date or default_start
    end = end_date or default_end
    if start > end or start.year != end.year or start.month != end.month:
        raise RuntimeError("Periodo report non valido.")
    crm_enabled = (
        manual_fetcher is None
        or mapping_fetcher is not None
        or crm_export_path is not None
    )
    manual_fetcher = manual_fetcher or fetch_manual_inputs
    mapping_fetcher = mapping_fetcher or fetch_crm_mapping_from_google_sheet
    google_fetcher = google_fetcher or fetch_google_campaign_delivery
    meta_fetcher = meta_fetcher or fetch_meta_campaign_delivery

    manual_rows = manual_fetcher()
    crm_allocations: dict[int, int] | None = None
    allocation_methods: dict[int, str] | None = None
    crm_normalized: list[dict] = []
    if crm_enabled:
        mapping_rows = mapping_fetcher()
        crm_path = Path(
            crm_export_path
            or os.getenv("CRM_EXPORT_PATH", "").strip()
            or ROOT / "data/input/LEAD QUESTO MESE PULITE 18-07-2026 11-09-08.xlsx"
        )
        if not crm_path.is_absolute():
            crm_path = ROOT / crm_path
        crm_leads = read_crm_export(crm_path, start, end)
        crm_allocations, allocation_methods, crm_normalized = match_crm_leads(
            crm_leads, manual_rows, mapping_rows
        )
    google_rows, google_verification, google_status, google_error = fetch_delivery_with_status(
        "Google Ads", google_fetcher, start.isoformat(), end.isoformat()
    )
    meta_rows, meta_verification, meta_status, meta_error = fetch_delivery_with_status(
        "Meta Ads", meta_fetcher, start.isoformat(), end.isoformat()
    )
    output_path = output_path if output_path.is_absolute() else ROOT / output_path
    _write_csv(ROOT / "data/raw/google_ads_raw.csv", google_rows, DELIVERY_COLUMNS)
    _write_csv(ROOT / "data/raw/meta_ads_raw.csv", meta_rows, DELIVERY_COLUMNS)
    _write_csv(
        ROOT / "data/raw/dynamics_raw.csv",
        crm_normalized,
        [
            "lead_id", "campaign_crm", "utm_campaign", "created_at",
            "match_status", "matched_excel_row", "lead_allocation_method",
        ],
    )
    verification_rows = google_verification + meta_verification
    _write_csv(
        ROOT / "data/raw/ads_delivery_verification.csv",
        verification_rows,
        ["platform", "campaign_id", "campaign_name", "periodo_interrogato",
         "speso_estratto", "stato_collegamento", "errore"],
    )

    settings = load_settings()
    errors = [error for error in (google_error, meta_error) if error]
    if errors:
        raise RuntimeError(
            "Aggiornamento interrotto: i collegamenti Ads non sono tutti disponibili. "
            "I file latest precedenti sono rimasti invariati."
        )

    rows = build_report_rows(
        manual_rows, google_rows, meta_rows, start, end,
        google_status=google_status, meta_status=meta_status, report_date=today,
        crm_leads_by_excel_row=crm_allocations,
        lead_allocation_methods=allocation_methods,
    )
    _write_csv(output_path, rows, REPORT_COLUMNS)
    metadata = {
        "client": settings.client_name,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "updated_at": datetime.now(ZoneInfo(settings.timezone)).isoformat(timespec="seconds"),
        "status": "success",
    }
    metadata_path = ROOT / "data/last_update.json"
    metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return output_path


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Genera il report Dynamica.")
    parser.add_argument("--start-date", type=date.fromisoformat)
    parser.add_argument("--end-date", type=date.fromisoformat)
    parser.add_argument("--today", type=date.fromisoformat)
    parser.add_argument("--crm-export", type=Path)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        path = build_report_data(
            today=args.today,
            start_date=args.start_date,
            end_date=args.end_date,
            crm_export_path=args.crm_export,
        )
    except Exception as exc:
        print(f"Errore: {exc}")
        return 1
    print(f"Report generato: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
