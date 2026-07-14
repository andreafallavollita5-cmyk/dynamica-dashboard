"""Read the manual campaign plan from Google Sheets.

This module is read-only: it never updates the spreadsheet. The Google Sheet is
the source of truth for manual campaign rows, while API delivery data is joined
later by other modules.
"""

from __future__ import annotations

import csv
import os
import sys
from pathlib import Path

import gspread
from dotenv import load_dotenv
from gspread.exceptions import APIError, SpreadsheetNotFound, WorksheetNotFound


ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"
RAW_OUTPUT_PATH = ROOT / "data" / "raw" / "google_sheet_raw.csv"

REQUIRED_COLUMNS = [
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
    "lead_effettive_manual",
    "action",
    "google_campaign_id",
    "meta_campaign_id",
    "dynamics_campaign_key",
    "enabled",
]

STRING_COLUMNS = {
    "funnel",
    "platform",
    "channel",
    "campaign_name",
    "action",
    "google_campaign_id",
    "meta_campaign_id",
    "dynamics_campaign_key",
    "enabled",
}

NUMERIC_COLUMNS = set(REQUIRED_COLUMNS) - STRING_COLUMNS
TRUE_VALUES = {"true", "1", "yes", "y", "si", "sì", "x"}
TARGET_ROW = {
    "funnel": "Lead Veloce",
    "platform": "Meta",
    "channel": "Display",
    "campaign_name": "DYN_VELOCE New Creative Apr26",
}


class GoogleSheetConfigError(RuntimeError):
    """Raised when local configuration is missing or invalid."""


class GoogleSheetReadError(RuntimeError):
    """Raised when the Google Sheet cannot be read correctly."""


def _load_sheet_config() -> dict[str, str]:
    if not ENV_PATH.exists():
        raise GoogleSheetConfigError(f"File .env non trovato: {ENV_PATH}")

    load_dotenv(ENV_PATH, encoding="utf-8-sig")
    config = {
        "sheet_id": os.getenv("GOOGLE_SHEET_ID", "").strip(),
        "worksheet_name": os.getenv(
            "GOOGLE_SHEET_WORKSHEET_NAME", "manual_inputs"
        ).strip(),
        "service_account_json_path": os.getenv(
            "GOOGLE_SERVICE_ACCOUNT_JSON_PATH", ""
        ).strip(),
    }

    missing = [key for key, value in config.items() if not value]
    if missing:
        raise GoogleSheetConfigError(
            "Variabili mancanti in .env: " + ", ".join(missing)
        )

    return config


def _resolve_service_account_path(path_value: str) -> Path:
    path = Path(path_value)
    if not path.is_absolute():
        path = ROOT / path
    if not path.exists():
        raise GoogleSheetConfigError(
            "Service account JSON non trovato nel percorso configurato."
        )
    return path


def _normalize_header(header: list[str]) -> list[str]:
    return [cell.strip() for cell in header]


def _validate_columns(columns: list[str]) -> None:
    missing = [column for column in REQUIRED_COLUMNS if column not in columns]
    if missing:
        raise GoogleSheetReadError(
            "Colonne obbligatorie mancanti nel worksheet manual_inputs: "
            + ", ".join(missing)
        )


def _parse_number(value: str) -> float | int | None | str:
    text = str(value).strip()
    if text == "":
        return None

    is_percent = text.endswith("%")
    cleaned = text.replace("€", "").replace(" ", "")
    cleaned = cleaned[:-1] if is_percent else cleaned
    if "," in cleaned and "." in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    else:
        cleaned = cleaned.replace(",", ".")

    try:
        number = float(cleaned)
    except ValueError:
        return value

    if is_percent:
        number = number / 100
    return int(number) if number.is_integer() else number


def _normalize_row(row: dict[str, str]) -> dict:
    normalized = dict(row)
    for column in REQUIRED_COLUMNS:
        value = normalized.get(column, "")
        if column in STRING_COLUMNS:
            normalized[column] = str(value).strip()
        elif column in NUMERIC_COLUMNS:
            normalized[column] = _parse_number(value)
    return normalized


def _is_enabled(row: dict) -> bool:
    return str(row.get("enabled", "")).strip().lower() in TRUE_VALUES


def _rows_from_values(values: list[list[str]]) -> list[dict]:
    if not values:
        raise GoogleSheetReadError("Worksheet manual_inputs vuoto.")

    columns = _normalize_header(values[0])
    if not all(column in columns for column in REQUIRED_COLUMNS):
        return _rows_from_legacy_dashboard(values)
    _validate_columns(columns)

    rows = []
    for raw_row in values[1:]:
        padded = raw_row + [""] * (len(columns) - len(raw_row))
        row = {column: padded[index] for index, column in enumerate(columns)}
        if any(str(value).strip() for value in row.values()):
            rows.append(_normalize_row(row))
    return rows


def _rows_from_legacy_dashboard(values: list[list[str]]) -> list[dict]:
    """Read the existing agency worksheet without changing its visual layout."""
    header = [str(value).strip().casefold() for value in values[0]]
    expected_markers = {"funnel", "id campagna", "campagna", "investimento media"}
    if not expected_markers.issubset(set(header)):
        _validate_columns(_normalize_header(values[0]))

    rows: list[dict] = []
    current_funnel = ""
    current_platform = ""
    current_channel = ""
    for excel_row, raw_row in enumerate(values[1:], start=2):
        padded = raw_row + [""] * max(0, 23 - len(raw_row))
        funnel = str(padded[0]).strip()
        platform = str(padded[1]).strip()
        channel = str(padded[2]).strip()
        campaign_id = str(padded[3]).strip()
        campaign_name = str(padded[4]).strip()

        if funnel and not funnel.casefold().startswith("tot "):
            current_funnel = funnel
        if platform:
            current_platform = platform
        if channel:
            current_channel = channel
        effective_platform = platform or current_platform
        effective_channel = channel or current_channel
        if not effective_platform or not campaign_name:
            continue

        platform_key = effective_platform.casefold()
        rows.append(
            _normalize_row(
                {
                    "excel_row": excel_row,
                    "funnel": funnel or current_funnel,
                    "platform": effective_platform,
                    "channel": effective_channel,
                    "campaign_name": campaign_name,
                    "investimento_media": padded[5],
                    "percentuale_investimento": padded[6],
                    "cpp_medio": padded[7],
                    "stima_pratiche": padded[8],
                    "cpl_target": padded[9],
                    "stima_lead": padded[10],
                    "lead_effettive_manual": padded[13],
                    "action": padded[22],
                    "google_campaign_id": campaign_id if "google" in platform_key else "",
                    "meta_campaign_id": campaign_id if "meta" in platform_key else "",
                    "dynamics_campaign_key": "",
                    "enabled": "true",
                }
            )
        )
    if not rows:
        raise GoogleSheetReadError(
            "Il worksheet non contiene righe campagna riconoscibili."
        )
    return rows


def _write_raw_csv(rows: list[dict], output_path: Path = RAW_OUTPUT_PATH) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys()) if rows else REQUIRED_COLUMNS
    with output_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return output_path


def fetch_manual_plan_from_google_sheet() -> list[dict]:
    """Fetch enabled manual plan rows from the configured Google Sheet.

    The raw rows are saved to `data/raw/google_sheet_raw.csv`; returned rows are
    filtered to `enabled=true`. Campaign IDs are always kept as strings.
    """
    config = _load_sheet_config()
    service_account_path = _resolve_service_account_path(
        config["service_account_json_path"]
    )

    try:
        client = gspread.service_account(filename=str(service_account_path))
        spreadsheet = client.open_by_key(config["sheet_id"])
        worksheet = spreadsheet.worksheet(config["worksheet_name"])
        values = worksheet.get_all_values()
    except SpreadsheetNotFound as exc:
        raise GoogleSheetReadError(
            "Google Sheet non trovato o non condiviso con il service account."
        ) from exc
    except WorksheetNotFound as exc:
        raise GoogleSheetReadError(
            f"Worksheet non trovato: {config['worksheet_name']}"
        ) from exc
    except APIError as exc:
        raise GoogleSheetReadError(
            "Errore Google API durante la lettura del foglio. "
            "Controlla permessi e condivisione."
        ) from exc
    except PermissionError as exc:
        raise GoogleSheetReadError(
            "Permesso negato: condividi il Google Sheet con il service account "
            "configurato nel JSON."
        ) from exc
    except Exception as exc:
        raise GoogleSheetReadError(
            "Impossibile leggere il Google Sheet con la configurazione attuale."
        ) from exc

    all_rows = _rows_from_values(values)
    _write_raw_csv(all_rows)
    return [row for row in all_rows if _is_enabled(row)]


def fetch_manual_inputs() -> list[dict]:
    """Backward-compatible alias for the manual plan reader."""
    return fetch_manual_plan_from_google_sheet()


def _matches_target(row: dict) -> bool:
    return all(str(row.get(key, "")).strip() == value for key, value in TARGET_ROW.items())


def main() -> int:
    """Run a safe read-only smoke test against the manual Google Sheet."""
    try:
        config = _load_sheet_config()
        service_account_path = _resolve_service_account_path(
            config["service_account_json_path"]
        )
        client = gspread.service_account(filename=str(service_account_path))
        worksheet = client.open_by_key(config["sheet_id"]).worksheet(
            config["worksheet_name"]
        )
        values = worksheet.get_all_values()
        columns = _normalize_header(values[0]) if values else []
        all_rows = _rows_from_values(values)
        _write_raw_csv(all_rows)
        enabled_rows = [row for row in all_rows if _is_enabled(row)]
    except (GoogleSheetConfigError, GoogleSheetReadError) as exc:
        print(f"Errore: {exc}", file=sys.stderr)
        return 1
    except PermissionError:
        print(
            "Errore: permesso negato. Condividi il Google Sheet con il service "
            "account configurato nel JSON.",
            file=sys.stderr,
        )
        return 1
    except Exception as exc:
        print(
            "Errore: test Google Sheet non completato. "
            "Controlla configurazione, permessi e worksheet.",
            file=sys.stderr,
        )
        return 1

    matches = [row for row in enabled_rows if _matches_target(row)]
    total_investment = sum(
        float(row.get("investimento_media") or 0)
        for row in matches
        if isinstance(row.get("investimento_media"), (int, float))
    )
    first_investment = matches[0].get("investimento_media") if matches else ""

    print(f"righe_totali={len(all_rows)}")
    print(f"righe_enabled_true={len(enabled_rows)}")
    print("colonne_trovate=" + ",".join(columns))
    print(f"riga_trovata={'si' if matches else 'no'}")
    print(f"numero_righe_trovate={len(matches)}")
    print(f"investimento_media_riga={first_investment}")
    print(f"totale_investimento_media={total_investment}")
    print(f"raw_csv={RAW_OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
