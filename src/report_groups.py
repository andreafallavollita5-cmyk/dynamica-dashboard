"""Shared client report group and official summary definitions."""

from __future__ import annotations

from collections.abc import Mapping


CLIENT_GROUPS = (
    ("area_clienti", "Area Clienti"),
    ("lead_veloce", "Lead Veloce"),
    ("dem", "DEM"),
)

SUMMARY_FIELDS = (
    "investimento_media",
    "percentuale_investimento",
    "cpp_medio",
    "stima_pratiche",
    "cpl_target",
    "stima_lead",
    "stima_lead_giornaliere",
    "stima_lead_progressiva",
    "lead_effettive",
    "delta_lead",
    "stima_spending_giornaliera",
    "stima_spending_progressiva",
    "speso_effettivo",
    "delta_speso",
    "delta_delivery_pct",
    "cpl_effettivo",
    "delta_cpl",
)


def client_subtotal_group(row: Mapping[str, object]) -> str:
    """Return the stable slug used by dashboard data and Excel subtotals."""
    funnel = str(row.get("funnel") or "").strip().casefold()
    platform = str(row.get("platform") or "").strip().casefold()
    channel = str(row.get("channel") or "").strip().casefold()
    if "area clienti" in funnel:
        return "area_clienti"
    if platform == "dem" or channel == "dem":
        return "dem"
    return "lead_veloce"
