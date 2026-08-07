"""Write official report values back to the legacy ``manual_inputs`` sheet.

The worksheet is intentionally treated as a fixed visual template: columns A:K
and W onward are protected manual areas, rows are never inserted/deleted, and
the CRM mapping worksheet is read only.  Values are matched by campaign ID;
the three untracked DEM campaigns use their exact campaign name as the only
documented fallback.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable

import gspread
import pandas as pd
from gspread.exceptions import APIError, SpreadsheetNotFound, WorksheetNotFound
from gspread.utils import ValueInputOption, ValueRenderOption

from src.google_sheets_client import (
    MAPPING_WORKSHEET_DEFAULT,
    _load_sheet_config,
    _resolve_service_account_path,
)
from src.dates import working_days_inclusive, working_days_in_month
from src.report_groups import is_dem_campaign


ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = ROOT / "data" / "report_data.csv"
TARGET_WORKSHEET = "manual_inputs"
BACKUP_PREFIX = "manual_inputs_writeback_backup_"
DEM_NAMES = {
    "DEM DYNAMICS ADVICE ME",
    "DEM DIGITOO",
    "DEM TIG",
}
SUBTOTAL_LABELS = ("TOT Area Clienti", "TOT Lead Veloce", "TOT DEM")
FIRST_WRITABLE_COLUMN = 12  # L
LAST_WRITABLE_COLUMN = 22  # V


class SheetWritebackError(RuntimeError):
    """Raised when the write-back cannot be proven safe."""


@dataclass(frozen=True)
class Period:
    start_date: date
    end_date: date

    @property
    def days_in_month(self) -> int:
        next_month = (
            date(self.start_date.year + 1, 1, 1)
            if self.start_date.month == 12
            else date(self.start_date.year, self.start_date.month + 1, 1)
        )
        return (next_month - self.start_date).days

    @property
    def elapsed_days(self) -> int:
        return (self.end_date - self.start_date).days + 1

    @property
    def dem_days_in_month(self) -> int:
        return working_days_in_month(self.start_date)

    @property
    def dem_elapsed_days(self) -> int:
        return working_days_inclusive(self.start_date, self.end_date)


@dataclass(frozen=True)
class PlannedUpdate:
    range: str
    values: list[list[object]]
    reason: str

    def as_gspread(self) -> dict[str, object]:
        return {"range": self.range, "values": self.values}


def _column_letter(number: int) -> str:
    result = ""
    while number:
        number, remainder = divmod(number - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _cell(row: int, column: int) -> str:
    return f"{_column_letter(column)}{row}"


def _padded(values: list[list[object]], rows: int, columns: int) -> list[list[object]]:
    result: list[list[object]] = []
    for row_index in range(rows):
        source = values[row_index] if row_index < len(values) else []
        result.append(list(source[:columns]) + [""] * max(0, columns - len(source)))
    return result


def _normal_id(value: object) -> str:
    text = str(value or "").strip()
    return text[:-2] if text.endswith(".0") and text[:-2].isdigit() else text


def _number(value: object, field: str) -> float | None:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError as exc:
        raise SheetWritebackError(f"Valore non numerico in {field}: {value!r}") from exc


def _formula_number(value: float) -> str:
    if float(value).is_integer():
        return str(int(value))
    return format(float(value), ".12g")


def _top_row_for_cell(row: int, column: int, merges: Iterable[dict]) -> int:
    for merge in merges:
        start_row = int(merge.get("startRowIndex", 0)) + 1
        end_row = int(merge.get("endRowIndex", 0))
        start_col = int(merge.get("startColumnIndex", 0)) + 1
        end_col = int(merge.get("endColumnIndex", 0))
        if start_row <= row <= end_row and start_col <= column <= end_col:
            return start_row
    return row


def _report_period(frame: pd.DataFrame, expected_end_date: date | None) -> Period:
    required = {"row_type", "start_date", "end_date", "campaign_name"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise SheetWritebackError(
            "Colonne mancanti in report_data.csv: " + ", ".join(missing)
        )
    starts = pd.to_datetime(frame["start_date"], errors="raise").dt.date.unique()
    ends = pd.to_datetime(frame["end_date"], errors="raise").dt.date.unique()
    if len(starts) != 1 or len(ends) != 1:
        raise SheetWritebackError("Il CSV contiene più periodi di reporting.")
    period = Period(starts[0], ends[0])
    month_start = period.end_date.replace(day=1)
    if period.start_date != month_start:
        raise SheetWritebackError("start_date non è il primo giorno del mese.")
    if expected_end_date and period.end_date != expected_end_date:
        raise SheetWritebackError(
            f"Il CSV termina il {period.end_date}, atteso {expected_end_date}."
        )
    if not 1 <= period.elapsed_days <= period.days_in_month:
        raise SheetWritebackError("Periodo CSV non valido.")
    return period


def _sheet_layout(
    values: list[list[object]],
) -> tuple[list[list[object]], dict[str, int], dict[str, tuple[int, int]], int]:
    """Discover campaign groups from labels instead of fixed sheet rows."""
    rows = _padded(values, max(len(values), 2), 23)
    subtotal_rows: dict[str, int] = {}
    for row_number, row in enumerate(rows[1:], start=2):
        label = str(row[0]).strip()
        if label in SUBTOTAL_LABELS:
            if label in subtotal_rows:
                raise SheetWritebackError(f"Subtotal duplicato in manual_inputs: {label}")
            subtotal_rows[label] = row_number
    missing = [label for label in SUBTOTAL_LABELS if label not in subtotal_rows]
    if missing:
        raise SheetWritebackError(
            "Subtotal mancanti in manual_inputs: " + ", ".join(missing)
        )
    ordered_rows = [subtotal_rows[label] for label in SUBTOTAL_LABELS]
    if ordered_rows != sorted(ordered_rows):
        raise SheetWritebackError("Ordine subtotal non valido in manual_inputs.")

    total_candidates = [
        row_number
        for row_number in range(ordered_rows[-1] + 1, len(rows) + 1)
        if not any(str(value).strip() for value in rows[row_number - 1][:5])
        and any(str(value).strip() for value in rows[row_number - 1][5:11])
    ]
    if not total_candidates:
        raise SheetWritebackError("Riga totale generale non trovata in manual_inputs.")
    total_row = total_candidates[0]

    group_ranges: dict[str, tuple[int, int]] = {}
    first_row = 2
    for label in SUBTOTAL_LABELS:
        subtotal_row = subtotal_rows[label]
        if subtotal_row <= first_row:
            raise SheetWritebackError(f"Nessuna campagna prima di {label}.")
        group_ranges[label] = (first_row, subtotal_row - 1)
        first_row = subtotal_row + 1
    if total_row != ordered_rows[-1] + 1:
        raise SheetWritebackError("Righe inattese tra TOT DEM e il totale generale.")
    return rows, subtotal_rows, group_ranges, total_row


def _sheet_indexes(
    rows: list[list[object]], total_row: int
) -> tuple[dict[str, int], dict[str, int]]:
    ids: dict[str, int] = {}
    names: dict[str, int] = {}
    duplicates: set[str] = set()
    for row_number in range(2, total_row):
        campaign_id = _normal_id(rows[row_number - 1][3])
        campaign_name = str(rows[row_number - 1][4]).strip()
        if campaign_id:
            if campaign_id in ids:
                duplicates.add(campaign_id)
            ids[campaign_id] = row_number
        if campaign_name:
            if campaign_name in names:
                raise SheetWritebackError(
                    f"Nome campagna duplicato in manual_inputs: {campaign_name}"
                )
            names[campaign_name] = row_number
    if duplicates:
        raise SheetWritebackError(
            "ID campagna duplicati in manual_inputs: " + ", ".join(sorted(duplicates))
        )
    return ids, names


def _campaign_target_row(
    report_row: pd.Series, ids: dict[str, int], names: dict[str, int]
) -> int:
    campaign_ids = [
        _normal_id(report_row.get(column, ""))
        for column in ("google_campaign_id", "meta_campaign_id")
    ]
    campaign_ids = [campaign_id for campaign_id in campaign_ids if campaign_id]
    name = str(report_row.get("campaign_name", "")).strip()
    if campaign_ids:
        if len(campaign_ids) != 1:
            raise SheetWritebackError(f"Più ID per la campagna {name!r}.")
        campaign_id = campaign_ids[0]
        if campaign_id not in ids:
            raise SheetWritebackError(
                f"ID campagna {campaign_id} ({name}) non trovato in manual_inputs."
            )
        return ids[campaign_id]
    if is_dem_campaign(report_row):
        if name not in names:
            raise SheetWritebackError(f"Campagna DEM non trovata: {name}")
        return names[name]
    raise SheetWritebackError(
        f"Campagna senza ID e non DEM nel CSV: {name or '<senza nome>'}"
    )


def _derived_formulas(
    row: int,
    period: Period,
    include_lead_plan: bool = True,
    *,
    dem_spending: bool = False,
) -> dict[int, str]:
    spending_month_days = (
        period.dem_days_in_month if dem_spending else period.days_in_month
    )
    spending_elapsed_days = (
        period.dem_elapsed_days if dem_spending else period.elapsed_days
    )
    lead_month_days = period.dem_days_in_month if dem_spending else period.days_in_month
    lead_elapsed_days = period.dem_elapsed_days if dem_spending else period.elapsed_days
    formulas = {
        16: f'=IF(F{row}="";"";F{row}/{spending_month_days})',
        17: f'=IF(P{row}="";"";P{row}*{spending_elapsed_days})',
        19: f'=IF(OR(R{row}="";Q{row}="");"";R{row}-Q{row})',
        20: f"=IFERROR(S{row}/Q{row})",
        21: f"=IFERROR(R{row}/N{row})",
        22: f'=IF(OR(U{row}="";J{row}="");"";U{row}-J{row})',
    }
    if include_lead_plan:
        formulas.update(
            {
                12: f'=IF(K{row}="";"";K{row}/{lead_month_days})',
                13: f'=IF(L{row}="";"";L{row}*{lead_elapsed_days})',
                15: f'=IF(OR(N{row}="";M{row}="");"";N{row}-M{row})',
            }
        )
    return formulas


def _summary_formulas(
    row: int,
    first: int,
    last: int,
    period: Period,
    *,
    dem_spending: bool = False,
) -> dict[int, str]:
    formulas = _derived_formulas(row, period, dem_spending=dem_spending)
    formulas[14] = f"=SUM(N{first}:N{last})"
    formulas[18] = f"=SUM(R{first}:R{last})"
    return formulas


def build_update_plan(
    frame: pd.DataFrame,
    sheet_values: list[list[object]],
    merges: list[dict],
    expected_end_date: date | None = None,
) -> tuple[Period, list[PlannedUpdate], dict[str, float]]:
    """Build and validate a write plan without contacting Google Sheets."""
    period = _report_period(frame, expected_end_date)
    rows, subtotal_rows, group_ranges, total_row = _sheet_layout(sheet_values)
    ids, names = _sheet_indexes(rows, total_row)
    campaigns = frame.loc[frame["row_type"].astype(str) == "campaign"].copy()
    if campaigns.empty:
        raise SheetWritebackError("report_data.csv non contiene righe campagna.")

    spend_groups: dict[int, dict[str, object]] = {}
    lead_groups: dict[int, dict[str, object]] = {}
    for _, report_row in campaigns.iterrows():
        physical_row = _campaign_target_row(report_row, ids, names)
        display_row = _top_row_for_cell(physical_row, 14, merges)
        spend_row = _top_row_for_cell(physical_row, 18, merges)
        if display_row != physical_row or spend_row != physical_row:
            raise SheetWritebackError(
                f"La campagna alla riga {physical_row} ha celle unite in N o R; "
                "le campagne devono essere indipendenti."
            )
        lead_bucket = lead_groups.setdefault(
            display_row, {"lead": 0.0, "names": []}
        )
        spend_bucket = spend_groups.setdefault(
            spend_row, {"spend": 0.0, "names": [], "dem": False}
        )
        lead = _number(report_row.get("lead_effettive"), "lead_effettive")
        spend = _number(report_row.get("speso_effettivo"), "speso_effettivo")
        lead_bucket["lead"] = float(lead_bucket["lead"]) + (lead or 0.0)
        lead_bucket["names"].append(str(report_row.get("campaign_name", "")))
        spend_bucket["spend"] = float(spend_bucket["spend"]) + (spend or 0.0)
        spend_bucket["names"].append(str(report_row.get("campaign_name", "")))
        is_dem = is_dem_campaign(report_row)
        spend_bucket["dem"] = bool(spend_bucket["dem"]) or is_dem
        if is_dem:
            cpl = _number(report_row.get("cpl_target"), "cpl_target")
            if lead is None or cpl is None or spend is None:
                raise SheetWritebackError("Lead, CPL o speso DEM mancanti nel CSV.")
            if not math.isclose(spend, lead * cpl, rel_tol=0, abs_tol=0.01):
                raise SheetWritebackError(
                    f"Speso DEM incoerente per {report_row['campaign_name']}: "
                    f"{spend} != {lead} × {cpl}."
                )

    updates: list[PlannedUpdate] = [
        PlannedUpdate("M1", [[f"Stima lead al {period.end_date:%d/%m}"]], "header"),
        PlannedUpdate(
            "Q1", [[f"Stima spending al {period.end_date:%d/%m}"]], "header"
        ),
        PlannedUpdate(
            "R1", [[f"Speso effettivo {period.end_date:%d/%m}"]], "header"
        ),
    ]

    for row, bucket in sorted(lead_groups.items()):
        lead = float(bucket["lead"])
        updates.append(
            PlannedUpdate(
                _cell(row, 14),
                [[int(lead) if lead.is_integer() else lead]],
                "lead ufficiali: " + " + ".join(bucket["names"]),
            )
        )

    for row, bucket in sorted(spend_groups.items()):
        if bucket["dem"]:
            updates.append(
                PlannedUpdate(_cell(row, 18), [[f"=N{row}*J{row}"]], "speso DEM")
            )
        else:
            spend = float(bucket["spend"])
            updates.append(
                PlannedUpdate(_cell(row, 18), [[spend]], "speso Ads ufficiale")
            )
        formulas = _derived_formulas(
            row, period, dem_spending=bool(bucket["dem"])
        )
        for column, formula in formulas.items():
            updates.append(PlannedUpdate(_cell(row, column), [[formula]], "formula"))

    for label in SUBTOTAL_LABELS:
        row = subtotal_rows[label]
        source = group_ranges[label]
        for column, formula in _summary_formulas(
            row, *source, period, dem_spending=label == "TOT DEM"
        ).items():
            updates.append(PlannedUpdate(_cell(row, column), [[formula]], label))

    area_official = frame.loc[
        (frame["row_type"] == "subtotal")
        & (frame["campaign_name"].astype(str) == "TOT Area Clienti")
    ]
    if len(area_official.index) != 1:
        raise SheetWritebackError(
            "Riga ufficiale TOT Area Clienti mancante o duplicata."
        )
    area_leads = _number(
        area_official.iloc[0].get("lead_effettive"), "TOT Area Clienti lead"
    )
    area_row = subtotal_rows["TOT Area Clienti"]
    updates = [update for update in updates if update.range != _cell(area_row, 14)]
    updates.append(
        PlannedUpdate(
            _cell(area_row, 14),
            [[area_leads or 0]],
            "TOT Area Clienti ufficiale",
        )
    )

    total_formulas = _derived_formulas(total_row, period)
    subtotal_refs = {
        column: "+".join(_cell(subtotal_rows[label], column) for label in SUBTOTAL_LABELS)
        for column in (12, 13, 14, 16, 17, 18)
    }
    total_formulas.update(
        {column: f"={reference}" for column, reference in subtotal_refs.items()}
    )
    for column, formula in total_formulas.items():
        updates.append(
            PlannedUpdate(_cell(total_row, column), [[formula]], "TOTALE GENERALE")
        )

    for update in updates:
        column = 0
        for char in update.range:
            if not char.isalpha():
                break
            column = column * 26 + ord(char.upper()) - 64
        if (
            not FIRST_WRITABLE_COLUMN <= column <= LAST_WRITABLE_COLUMN
        ):
            raise SheetWritebackError(
                f"Piano non sicuro: {update.range} non è una cella autorizzata."
            )

    official = frame.loc[frame["row_type"].isin(["subtotal", "total"])].copy()
    expected: dict[str, float] = {}
    for _, row in official.iterrows():
        name = str(row.get("campaign_name", "")).strip()
        if name in {*SUBTOTAL_LABELS, "TOTALE GENERALE"}:
            expected[f"{name}:lead"] = float(_number(row.get("lead_effettive"), "lead") or 0)
            expected[f"{name}:spend"] = float(_number(row.get("speso_effettivo"), "spend") or 0)
    return period, updates, expected


def _manual_sheet_metadata(spreadsheet: gspread.Spreadsheet) -> tuple[list[dict], dict]:
    metadata = spreadsheet.fetch_sheet_metadata()
    for sheet in metadata.get("sheets", []):
        if sheet.get("properties", {}).get("title") == TARGET_WORKSHEET:
            return list(sheet.get("merges", [])), sheet.get("properties", {})
    raise SheetWritebackError(f"Worksheet non trovato: {TARGET_WORKSHEET}")


def _ensure_initial_backup(
    spreadsheet: gspread.Spreadsheet, worksheet: gspread.Worksheet
) -> str:
    metadata = spreadsheet.fetch_sheet_metadata()
    existing = [
        sheet["properties"]["title"]
        for sheet in metadata.get("sheets", [])
        if sheet.get("properties", {}).get("title", "").startswith(BACKUP_PREFIX)
    ]
    if existing:
        return sorted(existing)[0]
    name = BACKUP_PREFIX + datetime.now().strftime("%Y%m%dT%H%M%S")
    backup = spreadsheet.duplicate_sheet(worksheet.id, new_sheet_name=name)
    backup.hide()
    return name


def _verify_results(
    worksheet: gspread.Worksheet,
    protected_before: list[list[object]],
    expected_merges: list[dict],
    properties_before: dict,
    expected: dict[str, float],
    spreadsheet: gspread.Spreadsheet,
) -> None:
    protected_after = worksheet.get(
        "A1:K66", value_render_option=ValueRenderOption.formula
    )
    protected_before_padded = _padded(protected_before, 66, 11)
    protected_after_padded = _padded(protected_after, 66, 11)
    for row_index in range(66):
        for column_index in range(11):
            if (
                protected_before_padded[row_index][column_index]
                != protected_after_padded[row_index][column_index]
            ):
                raise SheetWritebackError(
                    "Verifica fallita: una cella manuale fuori dai controlli "
                    "periodo è cambiata."
                )
    merges_after, properties_after = _manual_sheet_metadata(spreadsheet)
    if expected_merges != merges_after:
        raise SheetWritebackError("Verifica fallita: unioni celle inattese.")
    # Creating the required backup can move the tab index; that is not a
    # structural change to the source worksheet itself.
    structural_keys = ("gridProperties", "hidden", "sheetId")
    before_structure = {key: properties_before.get(key) for key in structural_keys}
    after_structure = {key: properties_after.get(key) for key in structural_keys}
    if before_structure != after_structure:
        raise SheetWritebackError("Verifica fallita: struttura worksheet modificata.")

    values = worksheet.get(
        "A1:V66", value_render_option=ValueRenderOption.unformatted
    )
    padded_values, subtotal_rows, _group_ranges, total_row = _sheet_layout(values)
    row_by_name = {**subtotal_rows, "TOTALE GENERALE": total_row}
    for name, row in row_by_name.items():
        for metric, column in (("lead", 14), ("spend", 18)):
            key = f"{name}:{metric}"
            if key not in expected:
                raise SheetWritebackError(f"Riga ufficiale mancante nel CSV: {name}")
            actual = _number(padded_values[row - 1][column - 1], key)
            if actual is None or not math.isclose(
                actual, expected[key], rel_tol=0, abs_tol=0.02
            ):
                raise SheetWritebackError(
                    f"Verifica {key} fallita: {actual} != {expected[key]}"
                )


def run_writeback(
    report_path: Path = REPORT_PATH,
    expected_end_date: date | None = None,
    dry_run: bool = False,
) -> dict[str, object]:
    config = _load_sheet_config()
    if config["worksheet_name"] != TARGET_WORKSHEET:
        raise SheetWritebackError(
            f"GOOGLE_SHEET_WORKSHEET_NAME deve essere {TARGET_WORKSHEET}."
        )
    service_account = _resolve_service_account_path(config["service_account_json_path"])
    try:
        client = gspread.service_account(filename=str(service_account))
        spreadsheet = client.open_by_key(config["sheet_id"])
        worksheet = spreadsheet.worksheet(TARGET_WORKSHEET)
        # Required read-only access: this worksheet must never be a write target.
        mapping_name = os.getenv(
            "GOOGLE_SHEET_MAPPING_WORKSHEET_NAME", MAPPING_WORKSHEET_DEFAULT
        ).strip()
        mapping = spreadsheet.worksheet(mapping_name)
        mapping.get("A1:J30", value_render_option=ValueRenderOption.unformatted)
        values = worksheet.get(
            "A1:W66", value_render_option=ValueRenderOption.formula
        )
        protected_before = worksheet.get(
            "A1:K66", value_render_option=ValueRenderOption.formula
        )
        merges, properties = _manual_sheet_metadata(spreadsheet)
    except (SpreadsheetNotFound, WorksheetNotFound, APIError) as exc:
        raise SheetWritebackError("Impossibile leggere il Google Sheet configurato.") from exc

    frame = pd.read_csv(report_path, dtype=str, keep_default_na=False)
    period, updates, expected = build_update_plan(
        frame, values, merges, expected_end_date=expected_end_date
    )
    expected_merges = merges
    result: dict[str, object] = {
        "status": "dry-run" if dry_run else "updated",
        "worksheet": TARGET_WORKSHEET,
        "mapping_mode": "read-only",
        "start_date": period.start_date.isoformat(),
        "end_date": period.end_date.isoformat(),
        "days_in_month": period.days_in_month,
        "elapsed_days": period.elapsed_days,
        "dem_days_in_month": period.dem_days_in_month,
        "dem_elapsed_days": period.dem_elapsed_days,
        "updates": len(updates),
        "ranges": [update.range for update in updates],
        "unmerged_lead_ranges": [],
    }
    if dry_run:
        result["backup"] = "not-created-in-dry-run"
        return result

    backup_name = _ensure_initial_backup(spreadsheet, worksheet)
    try:
        worksheet.batch_update(
            [update.as_gspread() for update in updates],
            value_input_option=ValueInputOption.user_entered,
        )
        _verify_results(
            worksheet,
            protected_before,
            expected_merges,
            properties,
            expected,
            spreadsheet,
        )
    except APIError as exc:
        raise SheetWritebackError("Scrittura Google Sheet fallita.") from exc
    result["backup"] = backup_name
    result["verified"] = True
    return result


def _default_end_date() -> date:
    return date.today() - timedelta(days=1)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--end-date",
        type=date.fromisoformat,
        help="Override controllato del periodo atteso (YYYY-MM-DD).",
    )
    args = parser.parse_args(argv)
    expected_end_date = args.end_date or _default_end_date()
    try:
        result = run_writeback(
            expected_end_date=expected_end_date, dry_run=args.dry_run
        )
    except (SheetWritebackError, FileNotFoundError, ValueError) as exc:
        print(f"Errore write-back Google Sheet: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
