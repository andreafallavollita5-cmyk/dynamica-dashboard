from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pandas as pd
from gspread.exceptions import WorksheetNotFound

import app
from src.build_future_plan import build_future_plan, build_future_plan_rows
from src.google_sheets_client import (
    monthly_manual_worksheet_name,
    resolve_manual_worksheet,
)
from src.dates import current_month_until_yesterday
from src.import_monthly_plan import reconcile_plan
from src.publish_to_github import _accessible_plan_files


def manual_row(**overrides):
    row = {
        "excel_row": 2,
        "funnel": "Lead Veloce",
        "platform": "Google",
        "channel": "Search",
        "campaign_name": "Campaign A",
        "investimento_media": 3000,
        "percentuale_investimento": 1,
        "cpp_medio": 300,
        "stima_pratiche": 10,
        "cpl_target": 30,
        "stima_lead": 100,
        "lead_effettive_manual": 99,
        "speso_effettivo_manual": 1234,
        "action": "",
        "google_campaign_id": "g-1",
        "meta_campaign_id": "",
        "microsoft_campaign_id": "",
        "dynamics_campaign_key": "",
        "enabled": "true",
    }
    row.update(overrides)
    return row


class FakeSpreadsheet:
    def __init__(self, names):
        self.names = set(names)

    def worksheet(self, name):
        if name not in self.names:
            raise WorksheetNotFound(name)
        return name


class MonthlyWorksheetTests(unittest.TestCase):
    def test_month_specific_worksheet_is_preferred_and_fallback_is_safe(self):
        self.assertEqual(
            monthly_manual_worksheet_name(date(2026, 11, 1)),
            "manual_inputs_2026-11",
        )
        with patch(
            "src.google_sheets_client._load_sheet_config",
            return_value={"worksheet_name": "manual_inputs"},
        ):
            self.assertEqual(
                resolve_manual_worksheet(
                    FakeSpreadsheet({"manual_inputs", "manual_inputs_2026-11"}),
                    date(2026, 11, 1),
                ),
                "manual_inputs_2026-11",
            )
            self.assertEqual(
                resolve_manual_worksheet(
                    FakeSpreadsheet({"manual_inputs"}), date(2026, 10, 1)
                ),
                "manual_inputs",
            )

    def test_rollover_dates_resolve_the_report_month_not_the_calendar_day(self):
        available = FakeSpreadsheet({"manual_inputs", "manual_inputs_2026-11"})
        with patch(
            "src.google_sheets_client._load_sheet_config",
            return_value={"worksheet_name": "manual_inputs"},
        ):
            cases = {
                date(2026, 10, 30): "manual_inputs",
                date(2026, 11, 1): "manual_inputs",
                date(2026, 11, 2): "manual_inputs_2026-11",
                date(2026, 12, 1): "manual_inputs_2026-11",
            }
            for today, expected in cases.items():
                report_start, _report_end = current_month_until_yesterday(today)
                self.assertEqual(
                    resolve_manual_worksheet(available, report_start), expected
                )


class PlanBuildTests(unittest.TestCase):
    def test_future_plan_has_no_actuals(self):
        rows = build_future_plan_rows([manual_row()], date(2026, 11, 1))
        campaign = next(row for row in rows if row["row_type"] == "campaign")
        self.assertEqual(campaign["stima_spending_progressiva"], 3000)
        self.assertEqual(campaign["stima_lead_progressiva"], 100)
        for field in app.PLAN_ACTUAL_FIELDS:
            self.assertIsNone(campaign[field])
        self.assertEqual(campaign["source_status"], "plan:future")

    def test_future_plan_files_and_metadata_are_complete(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            destination = build_future_plan(
                date(2026, 11, 1),
                root,
                manual_fetcher=lambda: [manual_row()],
            )
            metadata = json.loads((destination / "last_update.json").read_text())
            self.assertEqual(metadata["dataset_type"], "future_plan")
            self.assertFalse(metadata["actuals_available"])
            self.assertEqual(metadata["end_date"], "2026-11-30")
            daily = pd.read_csv(destination / "report_daily_metrics.csv")
            self.assertTrue(daily.empty)

    def test_future_period_recalculates_plan_and_keeps_actuals_blank(self):
        frame = pd.DataFrame(build_future_plan_rows([manual_row()], date(2026, 11, 1)))
        result = app.build_future_plan_period_frame(
            pd, frame, date(2026, 11, 1), date(2026, 11, 15)
        )
        campaign = result[result["row_type"] == "campaign"].iloc[0]
        self.assertEqual(float(campaign["stima_spending_progressiva"]), 1500)
        self.assertEqual(float(campaign["stima_lead_progressiva"]), 50)
        self.assertTrue(pd.isna(campaign["speso_effettivo"]))
        self.assertTrue(pd.isna(campaign["lead_effettive"]))


class PlanImportTests(unittest.TestCase):
    def test_all_ads_ids_are_recovered_and_dem_ids_remain_blank(self):
        rows = [
            {
                "campaign_name": "Google A",
                "platform": "Google",
                "funnel": "Lead Veloce",
                "channel": "Search",
                "values": [None] * 11,
            },
            {
                "campaign_name": "DEM TIG",
                "platform": "Dem",
                "funnel": "Lead Veloce",
                "channel": "DEM",
                "values": [None] * 11,
            },
        ]
        live = [["Funnel", "Canale", "Canale", "ID", "Campagna"]]
        live.append(["Lead Veloce", "Google", "Search", "123", "Google A"])
        result = reconcile_plan(rows, live)
        self.assertEqual(result["ads_with_id"], 1)
        self.assertEqual(result["dem_without_id"], 1)
        self.assertEqual(result["unresolved"], [])
        self.assertEqual(rows[0]["values"][3], "123")
        self.assertEqual(rows[1]["values"][3], "")


class PlanCatalogTests(unittest.TestCase):
    def _write_dataset(self, folder: Path, metadata: dict):
        folder.mkdir(parents=True, exist_ok=True)
        pd.DataFrame([manual_row(row_type="campaign")]).to_csv(
            folder / "report_data.csv", index=False
        )
        pd.DataFrame(columns=["date", "source"]).to_csv(
            folder / "report_daily_metrics.csv", index=False
        )
        (folder / "last_update.json").write_text(json.dumps(metadata))

    def test_latest_replaces_future_plan_for_same_month(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plans = root / "plans"
            latest = root / "latest"
            self._write_dataset(
                plans / "2026-11",
                {
                    "start_date": "2026-11-01",
                    "end_date": "2026-11-30",
                    "dataset_type": "future_plan",
                    "actuals_available": False,
                },
            )
            self._write_dataset(
                latest,
                {"start_date": "2026-11-01", "end_date": "2026-11-18"},
            )
            with (
                patch.object(app, "PLANS_PATH", plans),
                patch.object(app, "HISTORY_PATH", root / "history"),
                patch.object(app, "DATA_PATH", latest / "report_data.csv"),
                patch.object(
                    app, "REPORT_DAILY_PATH", latest / "report_daily_metrics.csv"
                ),
                patch.object(app, "LAST_UPDATE_PATH", latest / "last_update.json"),
            ):
                catalog = app.load_period_catalog()
            self.assertEqual(catalog["2026-11"]["dataset_type"], "latest")
            self.assertEqual(catalog["2026-11"]["end"], date(2026, 11, 18))

    def test_only_complete_plan_folders_are_publishable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            complete = root / "2026-11"
            incomplete = root / "2026-12"
            complete.mkdir()
            incomplete.mkdir()
            for name in (
                "report_data.csv",
                "report_daily_metrics.csv",
                "last_update.json",
            ):
                (complete / name).write_text("ok")
            (incomplete / "report_data.csv").write_text("no")
            self.assertEqual(len(_accessible_plan_files(root)), 3)


if __name__ == "__main__":
    unittest.main()
