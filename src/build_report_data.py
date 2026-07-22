"""Build the final ``data/report_data.csv`` from manual and Ads API data."""

from __future__ import annotations

import argparse
import calendar
import csv
import hashlib
import json
import math
from collections.abc import Callable
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from src.ads_verification import fetch_delivery_with_status
from src.config import load_settings
from src.crm_export_selector import select_crm_export
from src.crm_excel_client import read_crm_export
from src.crm_lead_matcher import match_crm_leads
from src.combined_campaigns import apply_combined_campaign_metrics
from src.dates import current_month_until_yesterday, weekdays_inclusive, weekdays_in_month
from src.dynamics_client import fetch_effective_leads
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
    "lead_effettive", "delta_lead", "stima_spending_giornaliera",
    "stima_spending_progressiva",
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
CRMFetcher = Callable[[str, str], list[dict]]


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
    if connection_status == "error":
        return None, f"{platform_key}:error"

    by_id, by_name = _index_delivery(api_rows)
    campaign_id = str(manual.get(id_column) or "").strip()
    if campaign_id:
        match = by_id.get(campaign_id)
        if match is None:
            if connection_status == "stale":
                return None, f"{platform_key}:stale_missing"
            return 0.0, f"{platform_key}:no_delivery"
        suffix = "stale" if connection_status == "stale" else "ok"
        return float(match.get("spend") or 0), f"{platform_key}:{suffix}"

    campaign_name = str(manual.get("campaign_name") or "").strip()
    name_matches = by_name.get(campaign_name.casefold(), [])
    if len(name_matches) == 1:
        suffix = "stale_name_fallback" if connection_status == "stale" else "ok_name_fallback"
        return float(name_matches[0].get("spend") or 0), f"{platform_key}:{suffix}"
    if len(name_matches) > 1:
        return None, f"{platform_key}:ambiguous_name"
    if connection_status == "stale":
        return None, f"{platform_key}:stale_missing"
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
        failed = any(statuses[key] == "error" for key, _ in platforms)
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
    area_clienti_total: float | None = None,
) -> list[dict]:
    """Pure merge/calculation function, kept injectable for technical mocks."""
    report_date = report_date or date.today()
    days_in_month = calendar.monthrange(start_date.year, start_date.month)[1]
    elapsed_days = max((end_date - start_date).days + 1, 0)
    dem_days_in_month = weekdays_in_month(start_date)
    dem_elapsed_days = weekdays_inclusive(start_date, end_date)
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
        is_area_clienti = client_subtotal_group(manual) == "area_clienti"
        lead_effettive = (
            None
            if crm_mode and is_area_clienti
            else _number(crm_leads_by_excel_row.get(excel_row, 0))
            if crm_mode
            else _number(manual.get("lead_effettive_manual"))
        )
        cpl_target = _number(manual.get("cpl_target"))
        is_dem = client_subtotal_group(manual) == "dem"

        if connection_failures[index]:
            speso_effettivo = None
        elif platforms:
            speso_effettivo = ads_spends[index]
        else:
            if crm_mode:
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
        spending_days_in_month = dem_days_in_month if is_dem else days_in_month
        spending_elapsed_days = dem_elapsed_days if is_dem else elapsed_days
        calculated_spending_progressiva = (
            investimento / spending_days_in_month * spending_elapsed_days
            if investimento is not None else None
        )
        calculated_spending_giornaliera = safe_divide(
            investimento, spending_days_in_month
        )
        stima_spending_giornaliera = (
            calculated_spending_giornaliera
            if crm_mode or is_dem
            else _sheet_value_or(
                manual, "stima_spending_giornaliera", calculated_spending_giornaliera
            )
        )
        stima_spending_progressiva = (
            calculated_spending_progressiva
            if crm_mode or is_dem
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
                "stima_spending_giornaliera": stima_spending_giornaliera,
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
                    ";".join(source_parts)
                    if source_parts
                    else "manual:no_ads_source"
                ),
                "lead_allocation_method": lead_allocation_methods.get(
                    excel_row,
                    "area_clienti_total"
                    if crm_mode and is_area_clienti else "crm_mapping",
                ),
            }
        )
    if not output:
        return output
    apply_combined_campaign_metrics(output)
    if crm_mode:
        return _append_official_rows(
            output,
            manual_rows=manual_rows,
            days_in_month=days_in_month,
            elapsed_days=elapsed_days,
            area_clienti_total=area_clienti_total,
        )

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
    spend_daily_plan = _sum(rows, "stima_spending_giornaliera")
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
        "stima_spending_giornaliera": spend_daily_plan,
        "stima_spending_progressiva": spend_plan,
        "speso_effettivo": spend,
        "delta_speso": delta_spend,
        "delta_delivery_pct": safe_divide(delta_spend, spend_plan),
        "cpl_effettivo": cpl,
        "delta_cpl": cpl - cpl_target if cpl is not None and cpl_target is not None else None,
        "source_status": status,
    }


def _append_official_rows(
    campaign_rows: list[dict],
    *,
    manual_rows: list[dict] | None = None,
    days_in_month: int | None = None,
    elapsed_days: int | None = None,
    area_clienti_total: float | None = None,
) -> list[dict]:
    output = list(campaign_rows)
    summaries: list[dict] = []
    for slug, label in CLIENT_GROUPS:
        group = [row for row in campaign_rows if client_subtotal_group(row) == slug]
        if group:
            summary = _summary_row(group, f"TOT {label}", "subtotal")
            if slug == "area_clienti" and manual_rows:
                first = manual_rows[0]
                lead_target = _number(
                    first.get("sheet_area_clienti_stima_lead_subtotal")
                )
                cpl_target = _number(
                    first.get("sheet_area_clienti_cpl_target_subtotal")
                )
                if lead_target is not None:
                    summary["stima_lead"] = lead_target
                    if days_in_month:
                        summary["stima_lead_giornaliere"] = (
                            lead_target / days_in_month
                        )
                        summary["stima_lead_progressiva"] = (
                            summary["stima_lead_giornaliere"] * (elapsed_days or 0)
                        )
                        if summary.get("lead_effettive") is not None:
                            summary["delta_lead"] = (
                                summary["lead_effettive"]
                                - summary["stima_lead_progressiva"]
                            )
                if cpl_target is not None:
                    summary["cpl_target"] = cpl_target
                summary["lead_effettive"] = area_clienti_total
                summary["delta_lead"] = (
                    area_clienti_total - summary["stima_lead_progressiva"]
                    if area_clienti_total is not None
                    and summary.get("stima_lead_progressiva") is not None
                    else None
                )
                summary["cpl_effettivo"] = safe_divide(
                    summary.get("speso_effettivo"), area_clienti_total
                )
                summary["delta_cpl"] = (
                    summary["cpl_effettivo"] - summary["cpl_target"]
                    if summary.get("cpl_effettivo") is not None
                    and summary.get("cpl_target") is not None
                    else None
                )
            summaries.append(summary)
            output.append(summary)
    total = _summary_row(campaign_rows, "TOTALE GENERALE", "total")
    for field in (
        "stima_lead", "stima_lead_giornaliere", "stima_lead_progressiva"
    ):
        values = [summary.get(field) for summary in summaries]
        if any(value is not None for value in values):
            total[field] = sum(value or 0 for value in values)
    summary_leads = [summary.get("lead_effettive") for summary in summaries]
    total["lead_effettive"] = (
        sum(value or 0 for value in summary_leads)
        if any(value is not None for value in summary_leads) else None
    )
    total["cpl_effettivo"] = safe_divide(
        total.get("speso_effettivo"), total.get("lead_effettive")
    )
    if total.get("lead_effettive") is not None and total.get("stima_lead_progressiva") is not None:
        total["delta_lead"] = total["lead_effettive"] - total["stima_lead_progressiva"]
    if total.get("investimento_media") is not None and total.get("stima_lead"):
        total["cpl_target"] = total["investimento_media"] / total["stima_lead"]
        if total.get("cpl_effettivo") is not None:
            total["delta_cpl"] = total["cpl_effettivo"] - total["cpl_target"]
    output.append(total)
    return output


def _write_csv(path: Path, rows: list[dict], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _pseudonymized_crm_audit(rows: list[dict]) -> list[dict]:
    """Remove the Dataverse GUID while preserving deterministic local auditability."""
    audit: list[dict] = []
    for row in rows:
        item = dict(row)
        lead_id = str(item.get("lead_id") or "")
        item["lead_id"] = hashlib.sha256(
            f"dynamica-retail:{lead_id}".encode("utf-8")
        ).hexdigest()
        audit.append(item)
    return audit


def _previous_campaign_rows(path: Path, start_date: date) -> list[dict]:
    """Read the latest report rows for the same month."""
    if not path.exists():
        return []
    try:
        with path.open("r", newline="", encoding="utf-8-sig") as stream:
            rows = list(csv.DictReader(stream))
    except (OSError, csv.Error):
        return []
    return [
        row
        for row in rows
        if str(row.get("start_date") or "") == start_date.isoformat()
    ]


def _previous_delivery(rows: list[dict], platform: str) -> list[dict]:
    id_column = f"{platform}_campaign_id"
    delivery: list[dict] = []
    for row in rows:
        campaign_id = str(row.get(id_column) or "").strip()
        spend = _number(row.get("speso_effettivo"))
        if not campaign_id or spend is None:
            continue
        delivery.append(
            {
                "campaign_id": campaign_id,
                "campaign_name": str(row.get("campaign_name") or ""),
                "spend": spend,
                "clicks": None,
                "impressions": None,
            }
        )
    return delivery


def _previous_crm_allocations(
    previous_rows: list[dict], manual_rows: list[dict]
) -> tuple[dict[int, float | None], dict[int, str]]:
    previous_by_row = {
        int(row["excel_row"]): _number(row.get("lead_effettive"))
        for row in previous_rows
        if str(row.get("excel_row") or "").strip().isdigit()
    }
    allocations: dict[int, float | None] = {}
    methods: dict[int, str] = {}
    for manual in manual_rows:
        excel_row = int(manual.get("excel_row") or 0)
        allocations[excel_row] = previous_by_row.get(excel_row)
        methods[excel_row] = "crm_stale"
    return allocations, methods


def _previous_area_clienti_total(previous_rows: list[dict]) -> float | None:
    for row in previous_rows:
        if str(row.get("campaign_name") or "").strip() == "TOT Area Clienti":
            return _number(row.get("lead_effettive"))
    return None


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
    crm_fetcher: CRMFetcher | None = None,
) -> Path:
    """Run the read-only sources and generate CSV plus safe update metadata."""
    today = today or date.today()
    default_start, default_end = current_month_until_yesterday(today)
    start = start_date or default_start
    end = end_date or default_end
    if start > end or start.year != end.year or start.month != end.month:
        raise RuntimeError("Periodo report non valido.")
    output_path = output_path if output_path.is_absolute() else ROOT / output_path
    previous_rows = _previous_campaign_rows(output_path, start)
    settings = load_settings()
    dynamics_mode = (settings.dynamics_enabled or crm_fetcher is not None) and (
        crm_export_path is None
    )
    crm_enabled = (
        dynamics_mode
        or crm_fetcher is not None
        or manual_fetcher is None
        or mapping_fetcher is not None
        or crm_export_path is not None
    )
    manual_fetcher = manual_fetcher or fetch_manual_inputs
    mapping_fetcher = mapping_fetcher or fetch_crm_mapping_from_google_sheet
    google_fetcher = google_fetcher or fetch_google_campaign_delivery
    meta_fetcher = meta_fetcher or fetch_meta_campaign_delivery

    manual_rows = manual_fetcher()
    crm_allocations: dict[int, float | None] | None = None
    allocation_methods: dict[int, str] | None = None
    crm_normalized: list[dict] = []
    crm_status = "disabled"
    crm_error: str | None = None
    crm_file: str | None = None
    crm_source: str | None = None
    crm_fetch_succeeded = False
    area_clienti_total: float | None = None
    if crm_enabled:
        try:
            if dynamics_mode:
                crm_leads = (crm_fetcher or fetch_effective_leads)(
                    start.isoformat(), end.isoformat()
                )
                crm_status = "ok"
                crm_source = "dynamics"
            else:
                selection = select_crm_export(end, explicit_path=crm_export_path)
                crm_leads = read_crm_export(selection.path, start, end)
                crm_file = selection.path.name
                crm_status = "stale" if selection.is_stale else "ok"
                crm_source = "excel"
                if selection.is_stale:
                    crm_error = (
                        "Export CRM non aggiornato fino alla data finale del report."
                    )
            mapping_rows = mapping_fetcher()
            crm_allocations, allocation_methods, crm_normalized = match_crm_leads(
                crm_leads, manual_rows, mapping_rows
            )
            area_clienti_total = float(sum(
                1 for row in crm_normalized
                if row.get("match_status") == "matched"
                and row.get("lead_allocation_method") == "area_clienti_total"
            ))
            crm_fetch_succeeded = True
        except Exception:
            crm_allocations, allocation_methods = _previous_crm_allocations(
                previous_rows, manual_rows
            )
            area_clienti_total = _previous_area_clienti_total(previous_rows)
            crm_status = "stale" if previous_rows else "unavailable"
            source_label = "Dynamics" if dynamics_mode else "Export CRM"
            crm_error = (
                f"{source_label} non disponibile; lead precedenti mantenute quando presenti."
            )
    google_rows, google_verification, google_status, google_error = fetch_delivery_with_status(
        "Google Ads", google_fetcher, start.isoformat(), end.isoformat()
    )
    meta_rows, meta_verification, meta_status, meta_error = fetch_delivery_with_status(
        "Meta Ads", meta_fetcher, start.isoformat(), end.isoformat()
    )
    _write_csv(ROOT / "data/raw/google_ads_raw.csv", google_rows, DELIVERY_COLUMNS)
    _write_csv(ROOT / "data/raw/meta_ads_raw.csv", meta_rows, DELIVERY_COLUMNS)
    if crm_fetch_succeeded:
        _write_csv(
            ROOT / "data/raw/dynamics_raw.csv",
            _pseudonymized_crm_audit(crm_normalized),
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

    if google_status == "error" and meta_status == "error":
        raise RuntimeError(
            "Aggiornamento interrotto: entrambi i collegamenti Ads non sono disponibili. "
            "I file latest precedenti sono rimasti invariati."
        )

    source_messages: list[str] = []
    if google_status == "error":
        google_rows = _previous_delivery(previous_rows, "google")
        google_status = "stale" if google_rows else "error"
        source_messages.append("Google Ads non aggiornato.")
    if meta_status == "error":
        meta_rows = _previous_delivery(previous_rows, "meta")
        meta_status = "stale" if meta_rows else "error"
        source_messages.append("Meta Ads non aggiornato.")
    if crm_error:
        source_messages.append(crm_error)

    rows = build_report_rows(
        manual_rows, google_rows, meta_rows, start, end,
        google_status=google_status, meta_status=meta_status, report_date=today,
        crm_leads_by_excel_row=crm_allocations,
        lead_allocation_methods=allocation_methods,
        area_clienti_total=area_clienti_total,
    )
    if crm_status in {"stale", "unavailable"}:
        for row in rows:
            current = str(row.get("source_status") or "").strip()
            row["source_status"] = ";".join(
                part for part in (current, f"crm:{crm_status}") if part
            )
    _write_csv(output_path, rows, REPORT_COLUMNS)
    metadata = {
        "client": settings.client_name,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "updated_at": datetime.now(ZoneInfo(settings.timezone)).isoformat(timespec="seconds"),
        "status": "partial" if source_messages else "success",
        "sources": {
            "google_ads": google_status,
            "meta_ads": meta_status,
            "crm": crm_status,
        },
        "crm_source": crm_source,
        "crm_file": crm_file,
    }
    if source_messages:
        metadata["error"] = " ".join(source_messages)
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
