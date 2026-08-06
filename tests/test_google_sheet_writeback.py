from __future__ import annotations

import unittest
from datetime import date

import pandas as pd

from src.writeback_google_sheet import (
    SheetWritebackError,
    build_update_plan,
)
from src.update_sheet_estimates import build_estimate_updates
from src.writeback_google_sheet import Period


def report_row(**overrides):
    row = {
        "row_type": "campaign",
        "start_date": "2026-07-01",
        "end_date": "2026-07-17",
        "campaign_name": "Campaign A",
        "google_campaign_id": "111",
        "meta_campaign_id": "",
        "lead_effettive": "10",
        "speso_effettivo": "100",
        "cpl_target": "10",
    }
    row.update(overrides)
    return row


def sheet_values():
    rows = [[""] * 23 for _ in range(66)]
    rows[0][3] = "ID Campagna"
    rows[0][4] = "Campagna"
    rows[1][3] = "111"
    rows[1][4] = "Campaign A"
    rows[2][0] = "TOT Area Clienti"
    rows[3][3] = "222"
    rows[3][4] = "Campaign B"
    rows[4][3] = "22822606735"
    rows[4][4] = "DYN_VELOCE Cessione del Quinto [Esatta]"
    rows[5][3] = "23990314506"
    rows[5][4] = "DYN_VELOCE Cessione del Quinto [Esatta] QUINTO DIGITALE"
    rows[6][0] = "TOT Lead Veloce"
    rows[7][4] = "DEM DYNAMICS ADVICE ME"
    rows[8][4] = "DEM DIGITOO"
    rows[9][4] = "DEM TIG"
    rows[10][0] = "TOT DEM"
    rows[11][5] = 1
    return rows


def official_rows():
    return [
        report_row(
            row_type="subtotal",
            campaign_name="TOT Area Clienti",
            google_campaign_id="",
            lead_effettive="0",
            speso_effettivo="0",
        ),
        report_row(
            row_type="subtotal",
            campaign_name="TOT Lead Veloce",
            google_campaign_id="",
            lead_effettive="30",
            speso_effettivo="300",
        ),
        report_row(
            row_type="subtotal",
            campaign_name="TOT DEM",
            google_campaign_id="",
            lead_effettive="5",
            speso_effettivo="40",
        ),
        report_row(
            row_type="total",
            campaign_name="TOTALE GENERALE",
            google_campaign_id="",
            lead_effettive="35",
            speso_effettivo="340",
        ),
    ]


class WritebackPlanTests(unittest.TestCase):
    def test_legacy_layout_uses_calendar_days_and_dem_weekdays(self):
        values = [[""] * 22 for _ in range(66)]
        values[0][:6] = ["Funnel", "Canale", "Canale", "ID", "Campagna", "Investimento"]
        values[1][:6] = ["Lead Veloce", "Google", "Search", "1", "Search", 3100]
        values[1][10] = 310
        values[1][11:17] = ["old", "old", "", "", "old", "old"]
        values[2][:6] = ["TOT Lead Veloce", "", "", "", "", 3100]
        values[2][10] = 310
        values[2][11:17] = ["old", "old", "", "", "old", "old"]
        values[3][:6] = ["Lead Veloce", "Dem", "DEM", "", "DEM test", 2100]
        values[3][10] = 210
        values[3][11:17] = ["old", "old", "", "", "old", "old"]
        values[4][:6] = ["TOT DEM", "", "", "", "", 2100]
        values[4][10] = 210
        values[4][11:17] = ["old", "old", "", "", "old", "old"]
        values[5][5] = "=F3+F5"
        values[5][10] = "=K3+K5"
        values[5][15:17] = ["old", "old"]
        values[23][10] = "controllo - funnel clienti + veloce"

        updates = build_estimate_updates(
            values, Period(date(2026, 8, 1), date(2026, 8, 5))
        )
        by_range = {update.range: update.values[0][0] for update in updates}

        self.assertEqual(by_range["H26"], 31)
        self.assertEqual(by_range["I26"], 21)
        self.assertEqual(by_range["K26"], 5)
        self.assertEqual(by_range["L26"], 3)
        self.assertEqual(by_range["Q2"], '=IF(P2="";"";P2*K$26)')
        self.assertEqual(by_range["P4"], '=IF(F4="";"";F4/I$26)')
        self.assertEqual(by_range["Q4"], '=IF(P4="";"";P4*L$26)')
        self.assertEqual(by_range["M4"], '=IF(L4="";"";L4*K$26)')
        self.assertEqual(by_range["P6"], "=P3+P5")
        self.assertEqual(by_range["Q6"], "=Q3+Q5")

    def test_merged_campaign_ids_and_period_controls_are_updated_safely(self):
        frame = pd.DataFrame(
            [
                report_row(),
                report_row(
                    campaign_name="Campaign B",
                    google_campaign_id="222",
                    lead_effettive="20",
                    speso_effettivo="200",
                ),
                report_row(
                    campaign_name="DEM DYNAMICS ADVICE ME",
                    google_campaign_id="",
                    lead_effettive="5",
                    speso_effettivo="40",
                    cpl_target="8",
                ),
                *official_rows(),
            ]
        )
        period, updates, _ = build_update_plan(
            frame, sheet_values(), [], expected_end_date=date(2026, 7, 17)
        )
        by_range = {update.range: update.values[0][0] for update in updates}
        self.assertEqual(period.elapsed_days, 17)
        self.assertEqual(by_range["N2"], 10)
        self.assertEqual(by_range["R2"], 100)
        self.assertEqual(by_range["N4"], 20)
        self.assertEqual(by_range["R4"], 200)
        self.assertEqual(by_range["R8"], "=N8*J8")
        self.assertEqual(by_range["L35"], 17)
        self.assertEqual(by_range["H26"], 31)
        self.assertEqual(by_range["I26"], 23)
        self.assertEqual(by_range["K26"], 17)
        self.assertEqual(by_range["L26"], 13)
        self.assertEqual(by_range["P2"], '=IF(F2="";"";F2/H$26)')
        self.assertEqual(by_range["Q2"], '=IF(P2="";"";P2*K$26)')
        self.assertEqual(by_range["P8"], '=IF(F8="";"";F8/I$26)')
        self.assertEqual(by_range["Q8"], '=IF(P8="";"";P8*L$26)')
        self.assertEqual(by_range["M8"], '=IF(L8="";"";L8*K$26)')
        self.assertEqual(by_range["P12"], "=P3+P7+P11")
        self.assertEqual(by_range["Q12"], "=Q3+Q7+Q11")
        self.assertEqual(by_range["N12"], "=N3+N7+N11")
        self.assertEqual(by_range["N3"], 0)
        control_cells = {"H26", "I26", "K26", "L26"}
        self.assertTrue(
            all(
                key in control_cells or 12 <= ord(key[0]) - 64 <= 22
                for key in by_range
            )
        )

    def test_full_previous_month_updates_all_period_controls(self):
        rows = [report_row(), *official_rows()]
        for row in rows:
            row["start_date"] = "2026-07-01"
            row["end_date"] = "2026-07-31"

        period, updates, _ = build_update_plan(
            pd.DataFrame(rows),
            sheet_values(),
            [],
            expected_end_date=date(2026, 7, 31),
        )
        by_range = {update.range: update.values[0][0] for update in updates}

        self.assertEqual(period.elapsed_days, 31)
        self.assertEqual(period.dem_elapsed_days, 23)
        self.assertEqual(by_range["H26"], 31)
        self.assertEqual(by_range["I26"], 23)
        self.assertEqual(by_range["K26"], 31)
        self.assertEqual(by_range["L26"], 23)

    def test_duplicate_sheet_id_aborts_before_writes(self):
        values = sheet_values()
        values[3][3] = "111"
        frame = pd.DataFrame([report_row(), *official_rows()])
        with self.assertRaisesRegex(SheetWritebackError, "duplicati"):
            build_update_plan(frame, values, [], date(2026, 7, 17))

    def test_non_dem_without_id_is_rejected(self):
        frame = pd.DataFrame(
            [report_row(google_campaign_id=""), *official_rows()]
        )
        with self.assertRaisesRegex(SheetWritebackError, "senza ID"):
            build_update_plan(frame, sheet_values(), [], date(2026, 7, 17))

    def test_dem_reference_in_descriptive_fields_enables_name_fallback(self):
        frame = pd.DataFrame(
            [
                report_row(
                    campaign_name="DEM DIGITOO",
                    google_campaign_id="",
                    platform="Email DEM",
                    lead_effettive="5",
                    speso_effettivo="40",
                    cpl_target="8",
                ),
                *official_rows(),
            ]
        )

        _, updates, _ = build_update_plan(
            frame, sheet_values(), [], date(2026, 7, 17)
        )
        by_range = {update.range: update.values[0][0] for update in updates}
        self.assertEqual(by_range["P9"], '=IF(F9="";"";F9/I$26)')
        self.assertEqual(by_range["Q9"], '=IF(P9="";"";P9*L$26)')

    def test_adjacent_campaigns_use_independent_formulas(self):
        frame = pd.DataFrame(
            [
                report_row(
                    excel_row=9,
                    campaign_name="DYN_VELOCE Cessione del Quinto [Esatta]",
                    google_campaign_id="22822606735",
                    lead_effettive="61",
                    speso_effettivo="5490",
                    cpl_target="38.5",
                ),
                report_row(
                    excel_row=10,
                    campaign_name=(
                        "DYN_VELOCE Cessione del Quinto [Esatta] QUINTO DIGITALE"
                    ),
                    google_campaign_id="23990314506",
                    lead_effettive="92",
                    speso_effettivo="",
                    cpl_target="",
                ),
                *official_rows(),
            ]
        )
        _, updates, expected = build_update_plan(
            frame, sheet_values(), [], date(2026, 7, 17)
        )
        by_range = {update.range: update.values[0][0] for update in updates}
        self.assertEqual(by_range["N5"], 61)
        self.assertEqual(by_range["N6"], 92)
        self.assertEqual(by_range["O5"], '=IF(OR(N5="";M5="");"";N5-M5)')
        self.assertEqual(by_range["U5"], '=IFERROR(R5/N5)')
        self.assertNotIn("campaign:5:lead", expected)


if __name__ == "__main__":
    unittest.main()
