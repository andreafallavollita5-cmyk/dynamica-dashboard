from __future__ import annotations

import unittest
from datetime import date

import pandas as pd

from src.writeback_google_sheet import SheetWritebackError, build_update_plan


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
    rows[2][3] = "222"
    rows[2][4] = "Campaign B"
    rows[24][4] = "DEM DYNAMICS ADVICE ME"
    rows[25][4] = "DEM DIGITOO"
    rows[26][4] = "DEM TIG"
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
    def test_merged_campaign_ids_are_aggregated_and_only_l_to_v_are_touched(self):
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
        merges = [
            {
                "startRowIndex": 1,
                "endRowIndex": 3,
                "startColumnIndex": 13,
                "endColumnIndex": 14,
            },
            {
                "startRowIndex": 1,
                "endRowIndex": 3,
                "startColumnIndex": 17,
                "endColumnIndex": 18,
            },
        ]
        period, updates, _ = build_update_plan(
            frame, sheet_values(), merges, expected_end_date=date(2026, 7, 17)
        )
        by_range = {update.range: update.values[0][0] for update in updates}
        self.assertEqual(period.elapsed_days, 17)
        self.assertEqual(by_range["N2"], 30)
        self.assertEqual(by_range["R2"], 300)
        self.assertEqual(by_range["R25"], "=N25*J25")
        self.assertEqual(by_range["L35"], 17)
        self.assertEqual(by_range["N29"], "=N7+N24+N28")
        self.assertEqual(by_range["N7"], 0)
        self.assertNotIn(",", by_range["P35"])
        self.assertTrue(all(12 <= ord(key[0]) - 64 <= 22 for key in by_range))

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


if __name__ == "__main__":
    unittest.main()
