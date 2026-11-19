"""Import a monthly agency Excel plan into a dedicated Google worksheet."""

from __future__ import annotations

import argparse
import calendar
import json
from datetime import date, datetime
from pathlib import Path

import gspread
from gspread.exceptions import WorksheetNotFound
from gspread.utils import ValueInputOption, ValueRenderOption
from openpyxl import load_workbook
from openpyxl.formula.translate import Translator

from src.dates import working_days_inclusive, working_days_in_month
from src.google_sheets_client import (
    _load_sheet_config,
    _resolve_service_account_path,
    monthly_manual_worksheet_name,
)


ROOT = Path(__file__).resolve().parents[1]
ADS_PLATFORM_MARKERS = ("google", "meta", "microsoft", "bing")
SOURCE_TO_TARGET_COLUMNS = {
    1: 1,
    2: 2,
    3: 3,
    4: 5,
    5: 6,
    6: 7,
    7: 8,
    8: 9,
    9: 10,
    10: 11,
}


def parse_month(value: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m").date().replace(day=1)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Il mese deve avere formato YYYY-MM.") from exc


def _translate_value(cell, target_coordinate: str):
    value = cell.value
    if isinstance(value, str) and value.startswith("="):
        return Translator(value, origin=cell.coordinate).translate_formula(
            target_coordinate
        )
    return value


def _source_rows(path: Path, sheet_name: str | None = None) -> list[dict]:
    formula_book = load_workbook(path, data_only=False, read_only=False)
    value_book = load_workbook(path, data_only=True, read_only=False)
    try:
        formula_sheet = formula_book[sheet_name] if sheet_name else formula_book.worksheets[0]
        value_sheet = value_book[formula_sheet.title]
        if str(formula_sheet.cell(3, 1).value or "").strip().casefold() != "funnel":
            raise ValueError("Header del piano non riconosciuto alla riga 3.")
        rows: list[dict] = []
        target_row = 2
        for source_row in range(4, formula_sheet.max_row + 1):
            raw = [formula_sheet.cell(source_row, col).value for col in range(1, 11)]
            cached = [value_sheet.cell(source_row, col).value for col in range(1, 11)]
            if not any(value not in (None, "") for value in raw):
                continue
            values: list[object] = [None] * 11
            for source_col, target_col in SOURCE_TO_TARGET_COLUMNS.items():
                cell = formula_sheet.cell(source_row, source_col)
                target_coordinate = gspread.utils.rowcol_to_a1(target_row, target_col)
                values[target_col - 1] = _translate_value(cell, target_coordinate)
            is_total = (
                not any(str(value or "").strip() for value in raw[:4])
                and raw[4] not in (None, "")
            )
            rows.append(
                {
                    "source_row": source_row,
                    "target_row": target_row,
                    "values": values,
                    "funnel": str(cached[0] or "").strip(),
                    "platform": str(cached[1] or "").strip(),
                    "channel": str(cached[2] or "").strip(),
                    "campaign_name": str(cached[3] or "").strip(),
                    "is_total": is_total,
                }
            )
            target_row += 1
            if is_total:
                break
        if not rows or not rows[-1]["is_total"]:
            raise ValueError("Riga totale del piano non trovata.")
        return rows
    finally:
        formula_book.close()
        value_book.close()


def _live_ids(values: list[list[object]]) -> dict[str, str]:
    ids: dict[str, str] = {}
    for raw in values[1:]:
        row = list(raw) + [""] * max(0, 5 - len(raw))
        campaign = str(row[4] or "").strip()
        campaign_id = str(row[3] or "").strip()
        if campaign and campaign_id:
            if campaign in ids and ids[campaign] != campaign_id:
                raise ValueError(f"ID duplicato e ambiguo per {campaign}.")
            ids[campaign] = campaign_id
    return ids


def _is_dem(row: dict) -> bool:
    return any(
        "dem" in str(row.get(field) or "").casefold()
        for field in ("funnel", "platform", "channel", "campaign_name")
    )


def reconcile_plan(rows: list[dict], live_values: list[list[object]]) -> dict:
    ids = _live_ids(live_values)
    ads_with_id = 0
    dem_without_id = 0
    unresolved: list[str] = []
    campaigns = 0
    for row in rows:
        name = row["campaign_name"]
        platform = row["platform"].casefold()
        if not name or not platform:
            continue
        campaigns += 1
        campaign_id = ids.get(name, "")
        if any(marker in platform for marker in ADS_PLATFORM_MARKERS):
            if not campaign_id:
                unresolved.append(name)
            else:
                ads_with_id += 1
                row["values"][3] = campaign_id
        elif _is_dem(row):
            dem_without_id += 1
            row["values"][3] = ""
    return {
        "campaigns": campaigns,
        "ads_with_id": ads_with_id,
        "dem_without_id": dem_without_id,
        "unresolved": unresolved,
    }


def _formula_updates(rows: list[dict], month_start: date) -> list[dict]:
    month_end = month_start.replace(
        day=calendar.monthrange(month_start.year, month_start.month)[1]
    )
    days = calendar.monthrange(month_start.year, month_start.month)[1]
    dem_days = working_days_in_month(month_start)
    elapsed = (month_end - month_start).days + 1
    dem_elapsed = working_days_inclusive(month_start, month_end)
    subtotal_rows: list[int] = []
    updates: list[dict] = []
    total_row = rows[-1]["target_row"]
    for row in rows[:-1]:
        number = row["target_row"]
        label = str(row["values"][0] or "").strip().casefold()
        if label.startswith("tot "):
            subtotal_rows.append(number)
        month_days = dem_days if _is_dem(row) or label == "tot dem" else days
        elapsed_days = dem_elapsed if _is_dem(row) or label == "tot dem" else elapsed
        updates.extend(
            [
                {"range": f"L{number}", "values": [[f'=IF(K{number}="";"";K{number}/{month_days})']]},
                {"range": f"M{number}", "values": [[f'=IF(L{number}="";"";L{number}*{elapsed_days})']]},
                {"range": f"P{number}", "values": [[f'=IF(F{number}="";"";F{number}/{month_days})']]},
                {"range": f"Q{number}", "values": [[f'=IF(P{number}="";"";P{number}*{elapsed_days})']]},
            ]
        )
    for column in ("L", "M", "P", "Q"):
        expression = "+".join(f"{column}{row}" for row in subtotal_rows)
        updates.append({"range": f"{column}{total_row}", "values": [[f"={expression}"]]})
    updates.extend(
        [
            {"range": "M1", "values": [[f"Stima lead al {month_end:%d/%m}"]]},
            {"range": "Q1", "values": [[f"Stima spending al {month_end:%d/%m}"]]},
            {"range": "R1", "values": [[f"Speso effettivo {month_end:%d/%m}"]]},
        ]
    )
    return updates


def import_monthly_plan(
    source: Path,
    month_start: date,
    *,
    source_sheet: str | None = None,
    dry_run: bool = False,
) -> dict:
    rows = _source_rows(source, source_sheet)
    config = _load_sheet_config()
    client = gspread.service_account(
        filename=str(_resolve_service_account_path(config["service_account_json_path"]))
    )
    spreadsheet = client.open_by_key(config["sheet_id"])
    base = spreadsheet.worksheet(config["worksheet_name"])
    live_values = base.get("A1:W66", value_render_option=ValueRenderOption.unformatted)
    reconciliation = reconcile_plan(rows, live_values)
    if reconciliation["unresolved"]:
        raise ValueError(
            "ID campagna non recuperabili: " + ", ".join(reconciliation["unresolved"])
        )
    target_name = monthly_manual_worksheet_name(month_start)
    result = {
        "status": "dry-run" if dry_run else "updated",
        "target_worksheet": target_name,
        **reconciliation,
    }
    if dry_run:
        return result

    try:
        target = spreadsheet.worksheet(target_name)
    except WorksheetNotFound:
        target = spreadsheet.duplicate_sheet(base.id, new_sheet_name=target_name)

    last_row = rows[-1]["target_row"]
    target.batch_clear([f"A2:W{last_row}"])
    matrix = [row["values"] for row in rows]
    target.update(
        matrix,
        f"A2:K{last_row}",
        value_input_option=ValueInputOption.user_entered,
    )
    target.batch_update(
        _formula_updates(rows, month_start),
        value_input_option=ValueInputOption.user_entered,
    )
    target.update(
        [[""] for _ in rows],
        f"W2:W{last_row}",
        value_input_option=ValueInputOption.user_entered,
    )

    verified = target.get(
        f"A1:W{last_row}", value_render_option=ValueRenderOption.formula
    )
    flattened = [str(value) for row in verified for value in row]
    if any("#REF!" in value for value in flattened):
        raise ValueError("Verifica fallita: formula #REF! nel worksheet mensile.")
    if len(verified) < last_row:
        raise ValueError("Verifica fallita: righe mensili incomplete.")
    result["worksheet_id"] = target.id
    result["rows"] = len(rows)
    result["verified"] = True
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--month", required=True, type=parse_month)
    parser.add_argument("--source-sheet")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = import_monthly_plan(
            args.source,
            args.month,
            source_sheet=args.source_sheet,
            dry_run=args.dry_run,
        )
    except Exception as exc:
        print(f"Errore import piano mensile: {exc}")
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
