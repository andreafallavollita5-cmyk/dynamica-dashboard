"""Select and validate the newest manually supplied CRM workbook."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from src.crm_excel_client import REQUIRED_COLUMNS


ROOT = Path(__file__).resolve().parents[1]
CRM_SHEET_NAME = "LEAD QUESTO MESE PULITE"


@dataclass(frozen=True)
class CRMExportSelection:
    path: Path
    modified_at: datetime
    is_stale: bool


def _is_valid_workbook(path: Path) -> bool:
    try:
        frame = pd.read_excel(path, sheet_name=CRM_SHEET_NAME, dtype=object)
    except Exception:
        return False
    if not all(column in frame.columns for column in REQUIRED_COLUMNS):
        return False
    lead_ids = frame["Id Lead"].fillna("").astype(str).str.strip()
    created_at = pd.to_datetime(frame["Data e ora di creazione"], errors="coerce")
    return not lead_ids.eq("").any() and not created_at.isna().any()


def select_crm_export(
    end_date: date,
    explicit_path: str | Path | None = None,
    input_dir: str | Path | None = None,
) -> CRMExportSelection:
    """Return the newest valid workbook and whether it is older than the report."""
    configured_path = str(explicit_path or os.getenv("CRM_EXPORT_PATH", "")).strip()
    if configured_path:
        candidate = Path(configured_path)
        if not candidate.is_absolute():
            candidate = ROOT / candidate
        candidates = [candidate]
    else:
        configured_dir = Path(
            input_dir or os.getenv("CRM_EXPORT_DIR", "data/input").strip() or "data/input"
        )
        if not configured_dir.is_absolute():
            configured_dir = ROOT / configured_dir
        candidates = [
            path
            for path in configured_dir.glob("*.xlsx")
            if not path.name.startswith("~$") and path.is_file()
        ]

    existing = [path for path in candidates if path.exists() and path.is_file()]
    existing.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    for path in existing:
        if not _is_valid_workbook(path):
            continue
        modified_at = datetime.fromtimestamp(path.stat().st_mtime).astimezone()
        return CRMExportSelection(
            path=path,
            modified_at=modified_at,
            is_stale=modified_at.date() < end_date,
        )
    raise FileNotFoundError(
        "Nessun export CRM Excel valido disponibile nella cartella configurata."
    )
