"""Compare Dynamics API leads with the manual CRM export without publishing files."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import date
from pathlib import Path

from src.crm_excel_client import read_crm_export
from src.crm_export_selector import select_crm_export
from src.crm_lead_matcher import match_crm_leads
from src.dates import current_month_until_yesterday
from src.dynamics_client import DynamicsError, fetch_effective_leads
from src.google_sheets_client import (
    fetch_crm_mapping_from_google_sheet,
    fetch_manual_inputs,
)


def _summary(
    leads: list[dict], manual_rows: list[dict], mapping_rows: list[dict]
) -> dict:
    allocations, _methods, audit = match_crm_leads(
        leads, manual_rows, mapping_rows
    )
    all_rows = sorted(int(row["excel_row"]) for row in manual_rows)
    statuses = Counter(str(row.get("match_status") or "") for row in audit)
    return {
        "total_leads": len(leads),
        "allocations": {str(row): int(allocations.get(row, 0)) for row in all_rows},
        "matched": statuses["matched"],
        "unmatched": statuses["unmatched"],
        "ambiguous": statuses["ambiguous"],
    }


def compare_dynamics_with_export(
    start: date,
    end: date,
    export_path: str | Path | None = None,
    *,
    dynamics_fetcher=fetch_effective_leads,
    manual_fetcher=fetch_manual_inputs,
    mapping_fetcher=fetch_crm_mapping_from_google_sheet,
) -> tuple[bool, dict]:
    """Return exact reconciliation outcome and privacy-safe aggregate details."""
    selection = select_crm_export(end, explicit_path=export_path)
    api_leads = dynamics_fetcher(start.isoformat(), end.isoformat())
    excel_leads = read_crm_export(selection.path, start, end)
    manual_rows = manual_fetcher()
    mapping_rows = mapping_fetcher()
    api = _summary(api_leads, manual_rows, mapping_rows)
    excel = _summary(excel_leads, manual_rows, mapping_rows)
    return api == excel, {
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "export_file": selection.path.name,
        "api": api,
        "excel": excel,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-date", type=date.fromisoformat)
    parser.add_argument("--end-date", type=date.fromisoformat)
    parser.add_argument("--crm-export", type=Path)
    args = parser.parse_args()
    default_start, default_end = current_month_until_yesterday(date.today())
    start = args.start_date or default_start
    end = args.end_date or default_end
    try:
        exact, details = compare_dynamics_with_export(
            start, end, args.crm_export
        )
    except DynamicsError as exc:
        print(f"Validazione Dynamics non completata: {exc}")
        return 2
    except Exception:
        print("Validazione Dynamics non completata: verificare configurazione e log locali.")
        return 2
    print(json.dumps(details, ensure_ascii=False, indent=2))
    print("Confronto esatto riuscito." if exact else "Confronto non coincidente.")
    return 0 if exact else 1


if __name__ == "__main__":
    raise SystemExit(main())
