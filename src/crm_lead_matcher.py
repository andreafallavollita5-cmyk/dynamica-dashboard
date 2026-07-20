"""Deterministic CRM lead matching against the Google Sheet mapping."""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from datetime import date, datetime, timedelta


AREA_CLIENTI_CAMPAIGN = "area clienti"
ADVICE_PLAN = "dem dynamics advice me"
DIGITOO_PLAN = "dem digitoo"


def normalize_text(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = text.encode("ascii", "ignore").decode("ascii").casefold().strip()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def normalize_utm(value: object) -> str:
    return normalize_text(str(value or "").split(";", 1)[0])


def _as_date(value: object) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value or "").strip()
    if not text:
        return None
    try:
        serial = float(text)
    except ValueError:
        serial = None
    if serial is not None:
        return (datetime(1899, 12, 30) + timedelta(days=serial)).date()
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _mapping_rules(manual_rows: list[dict], mapping_rows: list[dict]) -> list[dict]:
    planning = {
        normalize_text(row.get("campaign_name")): row
        for row in manual_rows
        if normalize_text(row.get("campaign_name"))
    }
    rules: list[dict] = []
    for mapping in mapping_rows:
        campaign_plan = str(mapping.get("campaign_plan") or "").strip()
        manual = planning.get(normalize_text(campaign_plan))
        if manual is None:
            continue
        campaign_aliases = [
            normalize_text(alias)
            for alias in re.split(
                r"\s*\+\s*", str(mapping.get("campaign_crm") or "").strip()
            )
            if normalize_text(alias)
        ]
        utm_aliases = [
            normalize_utm(value)
            for value in (
                mapping.get("utm_campaign_1"),
                mapping.get("utm_campaign_2"),
            )
            if normalize_utm(value)
        ]
        if normalize_text(campaign_plan) == DIGITOO_PLAN:
            utm_aliases = ["digitoo"]
        rules.append(
            {
                "excel_row": int(manual["excel_row"]),
                "funnel": normalize_text(manual.get("funnel")),
                "campaign_plan": normalize_text(campaign_plan),
                "campaign_aliases": campaign_aliases,
                "utm_aliases": utm_aliases,
                "start_date": _as_date(mapping.get("start_date")),
                "end_date": _as_date(mapping.get("end_date")),
            }
        )
    return rules


def match_crm_leads(
    leads: list[dict],
    manual_rows: list[dict],
    mapping_rows: list[dict],
) -> tuple[dict[int, int], dict[int, str], list[dict]]:
    """Return counts, allocation methods and auditable normalized CRM rows."""
    rules = _mapping_rules(manual_rows, mapping_rows)
    area_rules = sorted(
        [rule for rule in rules if rule["funnel"] == AREA_CLIENTI_CAMPAIGN],
        key=lambda rule: rule["excel_row"],
    )
    allocations: dict[int, int] = defaultdict(int)
    methods: dict[int, str] = {}
    normalized_rows: list[dict] = []

    area_leads = [
        lead
        for lead in leads
        if normalize_text(lead.get("campaign_crm")) == AREA_CLIENTI_CAMPAIGN
    ]
    area_ids = {str(lead["lead_id"]) for lead in area_leads}
    if area_leads and len(area_rules) != 5:
        raise ValueError("La ripartizione Area Clienti richiede esattamente 5 righe.")
    if area_rules:
        base, remainder = divmod(len(area_leads), len(area_rules))
        cursor = 0
        for position, rule in enumerate(area_rules):
            count = base + (1 if position < remainder else 0)
            allocations[rule["excel_row"]] += count
            methods[rule["excel_row"]] = "area_clienti_uniform"
            for lead in area_leads[cursor : cursor + count]:
                normalized_rows.append(
                    {
                        **lead,
                        "match_status": "matched",
                        "matched_excel_row": rule["excel_row"],
                        "lead_allocation_method": "area_clienti_uniform",
                    }
                )
            cursor += count

    for lead in leads:
        if str(lead["lead_id"]) in area_ids:
            continue
        campaign = normalize_text(lead.get("campaign_crm"))
        utm = normalize_utm(lead.get("utm_campaign"))
        created = lead["created_at"].date()
        candidates: list[dict] = []
        for rule in rules:
            if rule in area_rules:
                continue
            if rule["start_date"] and created < rule["start_date"]:
                continue
            if rule["end_date"] and created > rule["end_date"]:
                continue
            campaign_ok = campaign in rule["campaign_aliases"]
            if rule["campaign_plan"] == ADVICE_PLAN:
                matched = campaign_ok
            elif not utm and rule["campaign_aliases"]:
                matched = campaign_ok
            elif rule["campaign_aliases"] and rule["utm_aliases"]:
                matched = campaign_ok and utm in rule["utm_aliases"]
            elif rule["campaign_aliases"]:
                matched = campaign_ok
            elif rule["utm_aliases"]:
                matched = utm in rule["utm_aliases"]
            else:
                matched = False
            if matched:
                candidates.append(rule)

        status = "unmatched"
        matched_row: int | None = None
        if len(candidates) == 1:
            status = "matched"
            matched_row = candidates[0]["excel_row"]
            allocations[matched_row] += 1
            methods.setdefault(matched_row, "crm_mapping")
        elif len(candidates) > 1:
            status = "ambiguous"
        normalized_rows.append(
            {
                **lead,
                "match_status": status,
                "matched_excel_row": matched_row,
                "lead_allocation_method": "crm_mapping" if matched_row else "",
            }
        )

    return dict(allocations), methods, normalized_rows
