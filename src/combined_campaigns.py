"""Lead-metric rollups for legacy/new CRM campaign pairs."""

from __future__ import annotations

import math
from collections.abc import Iterable

from src.utils import safe_divide


# Stable planning rows in ``manual_inputs``.  Each pair is (legacy, new).
COMBINED_CAMPAIGN_PAIRS: tuple[tuple[int, int], ...] = (
    (9, 10),
    (11, 12),
    (13, 14),
)
COMBINED_CAMPAIGN_ROWS = frozenset(
    row for pair in COMBINED_CAMPAIGN_PAIRS for row in pair
)
COMBINED_PARENT_BY_ROW = {
    row: parent for parent, child in COMBINED_CAMPAIGN_PAIRS for row in (parent, child)
}


def _number(value: object) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _sum_present(rows: Iterable[dict], field: str) -> float | None:
    values = [_number(row.get(field)) for row in rows]
    return sum(value or 0 for value in values) if any(
        value is not None for value in values
    ) else None


def apply_combined_campaign_metrics(rows: list[dict]) -> list[dict]:
    """Roll up plan/delta/CPL while preserving separate effective-lead counts."""
    by_excel_row = {
        int(float(row["excel_row"])): row
        for row in rows
        if _number(row.get("excel_row")) is not None
    }
    for parent_row, child_row in COMBINED_CAMPAIGN_PAIRS:
        parent = by_excel_row.get(parent_row)
        child = by_excel_row.get(child_row)
        if parent is None or child is None:
            continue
        pair = (parent, child)
        for field in (
            "stima_lead",
            "stima_lead_giornaliere",
            "stima_lead_progressiva",
        ):
            parent[field] = _sum_present(pair, field)
            child[field] = None

        leads = _sum_present(pair, "lead_effettive")
        lead_plan = _number(parent.get("stima_lead_progressiva"))
        parent["delta_lead"] = (
            leads - lead_plan
            if leads is not None and lead_plan is not None else None
        )
        child["delta_lead"] = None

        spend = _sum_present(pair, "speso_effettivo")
        parent["cpl_effettivo"] = safe_divide(spend, leads)
        child["cpl_effettivo"] = None
        cpl_target = _number(parent.get("cpl_target"))
        parent["delta_cpl"] = (
            parent["cpl_effettivo"] - cpl_target
            if parent["cpl_effettivo"] is not None and cpl_target is not None
            else None
        )
        child["delta_cpl"] = None

        marker = f"crm_metrics_combined_with_excel_row_{child_row}"
        current = str(parent.get("source_status") or "").strip()
        if marker not in current.split(";"):
            parent["source_status"] = ";".join(
                part for part in (current, marker) if part
            )
    return rows
