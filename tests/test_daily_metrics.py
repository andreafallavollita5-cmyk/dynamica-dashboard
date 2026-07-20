from __future__ import annotations

import unittest
from datetime import datetime
from pathlib import Path

import pandas as pd

from src.build_daily_metrics import build_daily_metric_rows


class DailyMetricsTests(unittest.TestCase):
    def test_scheduler_builds_daily_metrics_before_writeback_and_exports(self):
        source = Path("run_daily_update.bat").read_text(encoding="utf-8")
        report = source.index("-m src.build_report_data")
        daily = source.index("-m src.build_daily_metrics")
        writeback = source.index("-m src.writeback_google_sheet")
        excel = source.index("-m src.update_excel")
        self.assertLess(report, daily)
        self.assertLess(daily, writeback)
        self.assertLess(writeback, excel)

    def test_output_has_only_aggregates_and_keeps_area_as_pool(self):
        report = pd.DataFrame(
            [
                {
                    "row_type": "campaign", "start_date": "2026-07-01",
                    "end_date": "2026-07-17", "excel_row": 8,
                    "campaign_name": "Mapped", "platform": "Google",
                    "google_campaign_id": "123", "meta_campaign_id": "",
                    "investimento_media": 100,
                }
            ]
        )
        spend = pd.DataFrame(
            [
                {
                    "date": "2026-07-02", "source": "google_ads",
                    "campaign_id": "123", "campaign_name": "Ads", "spend": 10,
                }
            ]
        )
        leads = [
            {
                "lead_id": "SECRET-1", "campaign_crm": "CRM", "utm_campaign": "x",
                "created_at": datetime(2026, 7, 2, 10), "match_status": "matched",
                "matched_excel_row": 8, "lead_allocation_method": "crm_mapping",
            },
            {
                "lead_id": "SECRET-2", "campaign_crm": "AREA CLIENTI", "utm_campaign": "",
                "created_at": datetime(2026, 7, 2, 11), "match_status": "matched",
                "matched_excel_row": 2,
                "lead_allocation_method": "area_clienti_uniform",
            },
        ]
        rows = build_daily_metric_rows(
            report, spend, leads, {"TOT Area Clienti": 467}
        )
        self.assertEqual(len(rows), 4)
        self.assertFalse(any("lead_id" in row for row in rows))
        area = next(row for row in rows if row["source"] == "crm_area_clienti")
        self.assertEqual(area["leads"], 1)
        self.assertEqual(area["excel_row"], "")
        planning = next(row for row in rows if row["source"] == "planning")
        self.assertEqual(planning["monthly_lead_target"], 467)


if __name__ == "__main__":
    unittest.main()
