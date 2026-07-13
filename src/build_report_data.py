"""Build the final `data/report_data.csv` dataset."""

from __future__ import annotations

from pathlib import Path


REPORT_COLUMNS = [
    "report_date",
    "start_date",
    "end_date",
    "excel_row",
    "funnel",
    "platform",
    "channel",
    "campaign_name",
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
    "stima_spending_progressiva",
    "speso_effettivo",
    "delta_speso",
    "delta_delivery_pct",
    "cpl_effettivo",
    "delta_cpl",
    "action",
    "google_campaign_id",
    "meta_campaign_id",
    "dynamics_campaign_key",
    "source_status",
]


def build_report_data(output_path: Path = Path("data/report_data.csv")) -> Path:
    """Build the final CSV.

    Not implemented yet: next phase will merge Google Sheet manual inputs with
    Google Ads, Meta Ads, and future CRM data.
    """
    pass
