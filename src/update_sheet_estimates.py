"""Update period controls and estimate formulas in ``manual_inputs``.

This lightweight step is independent from ``report_data.csv`` so it can run
before the report build.  It preserves the visual template and only replaces
the four period controls plus existing estimate formulas.
"""

from __future__ import annotations

import math
import sys
from datetime import date

import gspread
from gspread.exceptions import APIError, SpreadsheetNotFound, WorksheetNotFound
from gspread.utils import ValueInputOption, ValueRenderOption

from src.dates import current_month_until_yesterday
from src.google_sheets_client import (
    _load_sheet_config,
    _resolve_service_account_path,
)
from src.report_groups import is_dem_campaign
from src.writeback_google_sheet import (
    PlannedUpdate,
    Period,
    SheetWritebackError,
    _ensure_initial_backup,
    _padded,
)


TARGET_WORKSHEET = "manual_inputs"
CONTROL_CELLS = {"H26", "I26", "K26", "L26"}
ESTIMATE_COLUMNS = {12, 13, 16, 17}  # L, M, P, Q


def _cell(row: int, column: int) -> str:
    letters = ""
    while column:
        column, remainder = divmod(column - 1, 26)
        letters = chr(65 + remainder) + letters
    return f"{letters}{row}"


def _row_mapping(row: list[object]) -> dict[str, object]:
    values = list(row) + [""] * max(0, 22 - len(row))
    return {
        "funnel": values[0],
        "platform": values[1],
        "channel": values[2],
        "campaign_name": values[4],
    }


def build_estimate_updates(
    sheet_values: list[list[object]], period: Period
) -> list[PlannedUpdate]:
    """Build a safe formula plan for either supported visual planning layout."""
    rows = _padded(sheet_values, max(len(sheet_values), 29), 22)
    control_marker_row = next(
        (
            index
            for index, row in enumerate(rows, start=1)
            if any("controllo - funnel" in str(value).casefold() for value in row)
        ),
        len(rows) + 1,
    )
    planning_rows = [
        index
        for index in range(2, control_marker_row)
        if any(str(value).strip() for value in rows[index - 1][:11])
    ]
    if not planning_rows:
        raise SheetWritebackError("Nessuna riga di planning trovata in manual_inputs.")

    subtotal_rows = [
        index
        for index in planning_rows
        if str(rows[index - 1][0]).strip().casefold().startswith("tot ")
    ]
    total_candidates = [
        index
        for index in planning_rows
        if index > max(subtotal_rows, default=0)
        and not any(str(value).strip() for value in rows[index - 1][:5])
        and any(str(value).strip() for value in rows[index - 1][5:11])
    ]
    total_row = total_candidates[-1] if total_candidates else None

    updates = [
        PlannedUpdate("H26", [[period.days_in_month]], "giorni mese"),
        PlannedUpdate("I26", [[period.dem_days_in_month]], "giorni mese DEM"),
        PlannedUpdate("K26", [[period.elapsed_days]], "giorni trascorsi"),
        PlannedUpdate("L26", [[period.dem_elapsed_days]], "feriali DEM trascorsi"),
    ]

    for row_number in planning_rows:
        if row_number == total_row:
            continue
        row = rows[row_number - 1]
        dem = is_dem_campaign(_row_mapping(row))
        spending_month_days = "I$26" if dem else "H$26"
        spending_elapsed_days = "L$26" if dem else "K$26"
        formulas = {
            12: f'=IF(K{row_number}="";"";K{row_number}/H$26)',
            13: f'=IF(L{row_number}="";"";L{row_number}*K$26)',
            16: f'=IF(F{row_number}="";"";F{row_number}/{spending_month_days})',
            17: (
                f'=IF(P{row_number}="";"";'
                f'P{row_number}*{spending_elapsed_days})'
            ),
        }
        for column, formula in formulas.items():
            if str(row[column - 1]).strip():
                updates.append(
                    PlannedUpdate(_cell(row_number, column), [[formula]], "formula stima")
                )

    if total_row is not None and subtotal_rows:
        subtotal_refs = "+".join(f"P{row}" for row in subtotal_rows)
        total = rows[total_row - 1]
        if str(total[15]).strip():
            updates.append(
                PlannedUpdate(f"P{total_row}", [[f"={subtotal_refs}"]], "totale misto")
            )
        subtotal_refs = "+".join(f"Q{row}" for row in subtotal_rows)
        if str(total[16]).strip():
            updates.append(
                PlannedUpdate(f"Q{total_row}", [[f"={subtotal_refs}"]], "totale misto")
            )

    allowed = CONTROL_CELLS | {
        _cell(row, column)
        for row in planning_rows
        for column in ESTIMATE_COLUMNS
    }
    if any(update.range not in allowed for update in updates):
        raise SheetWritebackError("Piano formule stima fuori dalle celle autorizzate.")
    return updates


def run_update(today: date | None = None) -> dict[str, object]:
    start_date, end_date = current_month_until_yesterday(today)
    period = Period(start_date, end_date)
    config = _load_sheet_config()
    try:
        client = gspread.service_account(
            filename=str(_resolve_service_account_path(config["service_account_json_path"]))
        )
        spreadsheet = client.open_by_key(config["sheet_id"])
        worksheet = spreadsheet.worksheet(TARGET_WORKSHEET)
        _ensure_initial_backup(spreadsheet, worksheet)
        before = worksheet.get(
            "A1:V66", value_render_option=ValueRenderOption.formula
        )
        updates = build_estimate_updates(before, period)
        worksheet.batch_update(
            [update.as_gspread() for update in updates],
            value_input_option=ValueInputOption.user_entered,
        )
        after = worksheet.get(
            "A1:V66", value_render_option=ValueRenderOption.formula
        )
    except (APIError, SpreadsheetNotFound, WorksheetNotFound) as exc:
        raise SheetWritebackError("Aggiornamento stime Google Sheet non riuscito.") from exc

    before_rows = _padded(before, 66, 22)
    after_rows = _padded(after, 66, 22)
    authorized = {update.range for update in updates}
    for row_index in range(66):
        for column_index in range(22):
            coordinate = _cell(row_index + 1, column_index + 1)
            if coordinate not in authorized and before_rows[row_index][column_index] != after_rows[row_index][column_index]:
                raise SheetWritebackError(
                    f"Verifica fallita: modifica inattesa in {coordinate}."
                )

    controls = worksheet.get(
        "H26:L26", value_render_option=ValueRenderOption.unformatted
    )
    control_row = _padded(controls, 1, 5)[0]
    expected = (period.days_in_month, period.dem_days_in_month, period.elapsed_days, period.dem_elapsed_days)
    actual = (control_row[0], control_row[1], control_row[3], control_row[4])
    if any(not math.isclose(float(value), target) for value, target in zip(actual, expected)):
        raise SheetWritebackError("Verifica finale dei controlli periodo fallita.")
    return {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "updates": len(updates),
    }


def main() -> int:
    try:
        result = run_update()
    except (SheetWritebackError, ValueError) as exc:
        print(f"Errore aggiornamento stime Google Sheet: {exc}", file=sys.stderr)
        return 1
    print(
        "Stime Google Sheet aggiornate: "
        f"{result['start_date']} -> {result['end_date']} ({result['updates']} celle)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
