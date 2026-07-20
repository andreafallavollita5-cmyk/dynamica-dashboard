"""Read and validate the manual Dynamics/CRM Excel export."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd


REQUIRED_COLUMNS = (
    "Id Lead",
    "Campagna",
    "Data e ora di creazione",
    "Utm campaign",
)


class CRMExportError(RuntimeError):
    """Raised when the manual CRM export is missing or invalid."""


def _text(value: object) -> str:
    return "" if pd.isna(value) else str(value).strip()


def read_crm_export(
    path: str | Path,
    start_date: date,
    end_date: date,
) -> list[dict]:
    """Return one normalized record per unique lead in the inclusive period."""
    export_path = Path(path)
    if not export_path.exists():
        raise CRMExportError(f"Export CRM non trovato: {export_path}")

    try:
        frame = pd.read_excel(
            export_path,
            sheet_name="LEAD QUESTO MESE PULITE",
            dtype=object,
        )
    except Exception as exc:
        raise CRMExportError("Impossibile leggere l'export CRM.") from exc

    missing = [column for column in REQUIRED_COLUMNS if column not in frame.columns]
    if missing:
        raise CRMExportError("Colonne CRM mancanti: " + ", ".join(missing))

    frame = frame.copy()
    frame["Id Lead"] = frame["Id Lead"].fillna("").astype(str).str.strip()
    if frame["Id Lead"].eq("").any():
        raise CRMExportError("L'export CRM contiene Id Lead vuoti.")

    frame["Data e ora di creazione"] = pd.to_datetime(
        frame["Data e ora di creazione"], errors="coerce"
    )
    if frame["Data e ora di creazione"].isna().any():
        raise CRMExportError("L'export CRM contiene date di creazione non valide.")

    start = pd.Timestamp(start_date)
    end_exclusive = pd.Timestamp(end_date) + pd.Timedelta(days=1)
    frame = frame[
        (frame["Data e ora di creazione"] >= start)
        & (frame["Data e ora di creazione"] < end_exclusive)
    ].copy()
    frame = frame.sort_values(
        ["Data e ora di creazione", "Id Lead"], kind="stable"
    ).drop_duplicates("Id Lead", keep="first")

    rows: list[dict] = []
    for _, row in frame.iterrows():
        rows.append(
            {
                "lead_id": str(row["Id Lead"]).strip(),
                "campaign_crm": _text(row.get("Campagna")),
                "utm_campaign": _text(row.get("Utm campaign")),
                "created_at": row["Data e ora di creazione"].to_pydatetime(),
            }
        )
    return rows
