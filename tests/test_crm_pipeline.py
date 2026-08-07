from __future__ import annotations

import unittest
from datetime import date, datetime

import pandas as pd

from app import prepare_excel_export_frame
from src.build_report_data import build_report_rows
from src.crm_lead_matcher import match_crm_leads


def manual(excel_row: int, name: str, funnel: str = "Lead Veloce", **extra):
    row = {
        "excel_row": excel_row,
        "campaign_name": name,
        "funnel": funnel,
        "platform": "",
        "channel": "",
        "investimento_media": 100,
        "stima_lead": 10,
        "cpl_target": 8,
    }
    row.update(extra)
    return row


def mapping(plan: str, campaign: str = "", utm: str = "", **extra):
    row = {
        "campaign_plan": plan,
        "campaign_crm": campaign,
        "utm_campaign_1": utm,
        "utm_campaign_2": "",
        "start_date": "46204",
        "end_date": "46234",
    }
    row.update(extra)
    return row


def lead(number: int, campaign: str, utm: str = "", day: int = 10):
    return {
        "lead_id": f"L-{number}",
        "campaign_crm": campaign,
        "utm_campaign": utm,
        "created_at": datetime(2026, 7, day, 12),
    }


class CRMMatchingTests(unittest.TestCase):
    def test_area_clienti_is_counted_only_in_the_official_total(self):
        plans = [manual(row, f"Area {row}", "Area Clienti") for row in range(2, 7)]
        maps = [mapping(f"Area {row}", "AREA CLIENTI" if row == 2 else "") for row in range(2, 7)]
        leads = [lead(index, "AREA CLIENTI") for index in range(7)]

        allocations, methods, audit = match_crm_leads(leads, plans, maps)

        self.assertEqual(allocations, {})
        self.assertEqual(methods, {})
        self.assertEqual({item["match_status"] for item in audit}, {"matched"})
        self.assertEqual(
            {item["lead_allocation_method"] for item in audit},
            {"area_clienti_total"},
        )
        self.assertEqual({item["matched_excel_row"] for item in audit}, {None})

    def test_and_no_utm_fallback_advice_and_excel_serial_validity(self):
        plans = [
            manual(8, "Standard"),
            manual(25, "DEM DYNAMICS ADVICE ME", platform="Dem", channel="DEM"),
            manual(26, "DEM DIGITOO", platform="Dem", channel="DEM"),
        ]
        maps = [
            mapping("Standard", "CRM STANDARD", "wanted"),
            mapping(
                "DEM DYNAMICS ADVICE ME",
                "QUINTO DIGITALE [ADVICE ME] + DYNAMICS ADVICE ME",
                "advice me",
                utm_campaign_2="Dem",
            ),
            mapping("DEM DIGITOO", "QUINTO DIGITALE [DIGITOO]", "wrong-sheet-value"),
        ]
        leads = [
            lead(1, "CRM STANDARD", "wanted"),
            lead(2, "CRM STANDARD", "other"),
            lead(3, "CRM STANDARD", ""),
            lead(4, "DYNAMICS ADVICE ME", "anything"),
            lead(5, "QUINTO DIGITALE [DIGITOO]", "digitoo"),
            lead(6, "CRM STANDARD", "wanted", day=1),
        ]
        maps[0]["start_date"] = "46205"  # 2 July 2026

        allocations, _, audit = match_crm_leads(leads, plans, maps)

        self.assertEqual(allocations, {8: 2, 25: 1, 26: 1})
        statuses = {item["lead_id"]: item["match_status"] for item in audit}
        self.assertEqual(statuses["L-2"], "unmatched")
        self.assertEqual(statuses["L-6"], "unmatched")

    def test_one_lead_can_never_be_counted_twice(self):
        plans = [manual(8, "A"), manual(9, "B")]
        maps = [mapping("A", "SAME"), mapping("B", "SAME")]
        allocations, _, audit = match_crm_leads([lead(1, "SAME")], plans, maps)
        self.assertEqual(allocations, {})
        self.assertEqual(audit[0]["match_status"], "ambiguous")

    def test_missing_utm_on_split_campaign_uses_first_planning_row(self):
        plans = [manual(6, "First"), manual(7, "Second")]
        maps = [
            mapping("First", "QUINTO DIGITALE [GOOGLE]", "base"),
            mapping("Second", "QUINTO DIGITALE [GOOGLE]", "exact"),
        ]

        allocations, methods, audit = match_crm_leads(
            [lead(1, "QUINTO DIGITALE [GOOGLE]")], plans, maps
        )

        self.assertEqual(allocations, {6: 1})
        self.assertEqual(methods, {6: "crm_mapping"})
        self.assertEqual(audit[0]["match_status"], "matched")
        self.assertEqual(audit[0]["matched_excel_row"], 6)


class OfficialReportRowsTests(unittest.TestCase):
    def test_area_subtotal_plan_is_preserved_in_official_rows(self):
        plans = [
            manual(row, f"Area {row}", "Area Clienti", stima_lead=None)
            for row in range(2, 7)
        ]
        plans[0]["sheet_area_clienti_stima_lead_subtotal"] = 467
        plans[0]["sheet_area_clienti_cpl_target_subtotal"] = 45
        rows = build_report_rows(
            plans,
            [],
            [],
            date(2026, 7, 1),
            date(2026, 7, 17),
            crm_leads_by_excel_row={row: 1 for row in range(2, 7)},
            area_clienti_total=5,
        )
        subtotal = next(row for row in rows if row["row_type"] == "subtotal")
        total = next(row for row in rows if row["row_type"] == "total")
        self.assertEqual(subtotal["stima_lead"], 467)
        self.assertAlmostEqual(subtotal["stima_lead_progressiva"], 467 / 31 * 17)
        self.assertEqual(subtotal["cpl_target"], 45)
        self.assertEqual(subtotal["lead_effettive"], 5)
        self.assertEqual(total["stima_lead"], 467)
        self.assertEqual(total["lead_effettive"], 5)
        campaigns = [row for row in rows if row["row_type"] == "campaign"]
        self.assertTrue(all(row["lead_effettive"] is None for row in campaigns))

    def test_official_cpp_and_practices_are_preserved_with_crm_rows(self):
        plans = [
            manual(2, "Area", "Area Clienti", stima_lead=None),
            manual(8, "Lead", "Lead Veloce", stima_lead=100),
        ]
        plans[0].update(
            {
                "sheet_area_clienti_cpp_medio_subtotal": 418,
                "sheet_area_clienti_stima_pratiche_subtotal": 44,
                "sheet_lead_veloce_cpp_medio_subtotal": 850,
                "sheet_lead_veloce_stima_pratiche_subtotal": 23.55,
                "sheet_total_cpp_medio": 496.82,
                "sheet_total_stima_pratiche": 67.55,
            }
        )
        rows = build_report_rows(
            plans,
            [],
            [],
            date(2026, 8, 1),
            date(2026, 8, 6),
            crm_leads_by_excel_row={8: 0},
            area_clienti_total=0,
        )
        subtotals = {
            row["funnel"]: row for row in rows if row["row_type"] == "subtotal"
        }
        total = next(row for row in rows if row["row_type"] == "total")
        self.assertEqual(subtotals["TOT Area Clienti"]["cpp_medio"], 418)
        self.assertEqual(subtotals["TOT Area Clienti"]["stima_pratiche"], 44)
        self.assertEqual(subtotals["TOT Lead Veloce"]["cpp_medio"], 850)
        self.assertEqual(subtotals["TOT Lead Veloce"]["stima_pratiche"], 23.55)
        self.assertEqual(total["cpp_medio"], 496.82)
        self.assertEqual(total["stima_pratiche"], 67.55)

    def test_dem_spend_and_official_rows_are_not_repeated_on_campaigns(self):
        rows = build_report_rows(
            [
                manual(8, "Google", google_campaign_id="123", platform="Google"),
                manual(25, "DEM", platform="Dem", channel="DEM", cpl_target=8),
            ],
            [{"campaign_id": "123", "campaign_name": "Google", "spend": 50}],
            [],
            date(2026, 7, 1),
            date(2026, 7, 17),
            crm_leads_by_excel_row={8: 2, 25: 3},
        )
        campaigns = [row for row in rows if row["row_type"] == "campaign"]
        total = [row for row in rows if row["row_type"] == "total"]
        self.assertEqual(len(campaigns), 2)
        self.assertEqual(len(total), 1)
        self.assertEqual(campaigns[1]["speso_effettivo"], 24)
        self.assertAlmostEqual(campaigns[1]["stima_spending_progressiva"], 100 / 23 * 13)
        self.assertEqual(total[0]["lead_effettive"], 5)
        self.assertFalse(any(key.startswith("kpi_") for key in campaigns[0]))

    def test_dem_spending_estimate_excludes_weekends_but_not_weekdays(self):
        rows = build_report_rows(
            [manual(25, "DEM", platform="Dem", channel="DEM", investimento_media=2300)],
            [],
            [],
            date(2026, 7, 1),
            date(2026, 7, 21),
            crm_leads_by_excel_row={25: 0},
        )
        campaign = next(row for row in rows if row["row_type"] == "campaign")
        self.assertEqual(campaign["stima_spending_giornaliera"], 100)
        self.assertEqual(campaign["stima_spending_progressiva"], 1500)

    def test_official_period_excel_download_does_not_recalculate_rows(self):
        frame = pd.DataFrame(
            [
                {
                    "row_type": "campaign",
                    "start_date": "2026-07-01",
                    "end_date": "2026-07-17",
                    "campaign_name": "A",
                    "speso_effettivo": 50,
                },
                {
                    "row_type": "total",
                    "start_date": "2026-07-01",
                    "end_date": "2026-07-17",
                    "campaign_name": "TOTALE GENERALE",
                    "speso_effettivo": 50,
                },
            ]
        )
        daily = pd.DataFrame(
            [{"date": date(2026, 7, 1), "campaign_name": "A", "spend": 999}]
        )
        exported = prepare_excel_export_frame(
            pd,
            frame,
            daily,
            {"start_date": "2026-07-01", "end_date": "2026-07-17"},
            date(2026, 7, 1),
            date(2026, 7, 17),
        )
        self.assertEqual(exported["speso_effettivo"].tolist(), [50, 50])
        self.assertEqual(exported["row_type"].tolist(), ["campaign", "total"])


if __name__ == "__main__":
    unittest.main()
