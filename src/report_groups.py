"""Shared client report group and official summary definitions."""

from __future__ import annotations

from collections.abc import Mapping
import re


CLIENT_GROUPS = (
    ("area_clienti", "Area Clienti"),
    ("lead_veloce", "Lead Veloce"),
    ("dem", "DEM"),
)

PROVISIONAL_EXCLUDED_CAMPAIGN = "PRESTITI PENSIONATI [GOOGLE ADS] — PROVVISORIA"

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


DEM_REFERENCE = re.compile(r"(?<![0-9a-z])dem(?![0-9a-z])", re.IGNORECASE)


def is_dem_campaign(row: Mapping[str, object]) -> bool:
    """Return whether any descriptive campaign field contains a DEM reference."""
    return any(
        DEM_REFERENCE.search(str(row.get(field) or "")) is not None
        for field in ("funnel", "platform", "channel", "campaign_name")
    )


def is_excluded_from_kpis(row: Mapping[str, object]) -> bool:
    """Return whether a visible campaign row must stay outside KPI totals."""
    explicit = str(row.get("exclude_from_kpi") or "").strip().casefold()
    if explicit in {"true", "1", "yes", "si", "sì"}:
        return True
    if explicit in {"false", "0", "no"}:
        return False
    campaign_name = str(row.get("campaign_name") or "").strip().casefold()
    return campaign_name == PROVISIONAL_EXCLUDED_CAMPAIGN.casefold()


def client_subtotal_group(row: Mapping[str, object]) -> str:
    """Return the stable slug used by dashboard data and Excel subtotals."""
    funnel = str(row.get("funnel") or "").strip().casefold()
    if "area clienti" in funnel:
        return "area_clienti"
    if is_dem_campaign(row):
        return "dem"
    return "lead_veloce"
