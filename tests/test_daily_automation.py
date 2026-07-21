from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path
from unittest.mock import patch

import pandas as pd

import src.build_report_data as report_module
from src.build_report_data import REPORT_COLUMNS, build_report_data
from src.crm_export_selector import select_crm_export
from src.dates import current_month_until_yesterday


def manual_row(**overrides):
    row = {
        "excel_row": 2,
        "funnel": "Lead Veloce",
        "platform": "Google",
        "channel": "Search",
        "campaign_name": "Google campaign",
        "investimento_media": 1000,
        "cpl_target": 20,
        "stima_lead": 50,
        "lead_effettive_manual": 4,
        "google_campaign_id": "g-1",
        "meta_campaign_id": "",
        "enabled": True,
    }
    row.update(overrides)
    return row


def write_crm(path: Path, *, valid: bool = True) -> None:
    columns = {
        "Id Lead": ["lead-1"],
        "Campagna": ["Campaign"],
        "Data e ora di creazione": [datetime(2026, 7, 10, 10, 0)],
        "Utm campaign": ["utm"],
    }
    if not valid:
        columns.pop("Id Lead")
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        pd.DataFrame(columns).to_excel(
            writer, sheet_name="LEAD QUESTO MESE PULITE", index=False
        )


class DateAutomationTests(unittest.TestCase):
    def test_first_day_closes_previous_month(self):
        self.assertEqual(
            current_month_until_yesterday(date(2026, 8, 1)),
            (date(2026, 7, 1), date(2026, 7, 31)),
        )

    def test_other_days_use_current_month(self):
        self.assertEqual(
            current_month_until_yesterday(date(2026, 8, 2)),
            (date(2026, 8, 1), date(2026, 8, 1)),
        )


class CRMSelectionTests(unittest.TestCase):
    def test_newest_valid_file_is_selected_and_lock_file_is_ignored(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            older = folder / "crm-old.xlsx"
            invalid = folder / "crm-new-invalid.xlsx"
            lock = folder / "~$crm-lock.xlsx"
            write_crm(older)
            write_crm(invalid, valid=False)
            lock.write_bytes(b"not an excel file")
            os.utime(older, (1_783_718_400, 1_783_718_400))  # 2026-07-10
            os.utime(invalid, (1_784_404_800, 1_784_404_800))
            os.utime(lock, (1_784_491_200, 1_784_491_200))

            selected = select_crm_export(date(2026, 7, 20), input_dir=folder)

            self.assertEqual(selected.path, older)
            self.assertTrue(selected.is_stale)

    def test_no_valid_workbook_has_a_safe_error(self):
        with tempfile.TemporaryDirectory() as temp:
            invalid = Path(temp) / "invalid.xlsx"
            write_crm(invalid, valid=False)
            with self.assertRaisesRegex(FileNotFoundError, "Nessun export CRM"):
                select_crm_export(date(2026, 7, 20), input_dir=temp)


class PartialAdsTests(unittest.TestCase):
    def test_one_failed_api_uses_only_same_month_previous_value(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            output = root / "data" / "report_data.csv"
            output.parent.mkdir(parents=True)
            previous = {
                column: "" for column in REPORT_COLUMNS
            }
            previous.update(
                {
                    "row_type": "campaign",
                    "start_date": "2026-07-01",
                    "end_date": "2026-07-19",
                    "excel_row": "2",
                    "campaign_name": "Google campaign",
                    "google_campaign_id": "g-1",
                    "speso_effettivo": "123.45",
                    "lead_effettive": "4",
                }
            )
            pd.DataFrame([previous], columns=REPORT_COLUMNS).to_csv(
                output, index=False, encoding="utf-8-sig"
            )
            rows = [
                manual_row(),
                manual_row(
                    excel_row=3,
                    platform="Meta",
                    campaign_name="Meta campaign",
                    google_campaign_id="",
                    meta_campaign_id="m-1",
                ),
            ]

            def fail_google(start, end):
                raise RuntimeError("secret technical failure")

            with patch.object(report_module, "ROOT", root):
                build_report_data(
                    output_path=output,
                    today=date(2026, 7, 21),
                    manual_fetcher=lambda: rows,
                    google_fetcher=fail_google,
                    meta_fetcher=lambda start, end: [
                        {"campaign_id": "m-1", "campaign_name": "Meta", "spend": 50}
                    ],
                )

            result = pd.read_csv(output, dtype=str, keep_default_na=False)
            google = result[result["google_campaign_id"] == "g-1"].iloc[0]
            meta = result[result["meta_campaign_id"] == "m-1"].iloc[0]
            self.assertEqual(float(google["speso_effettivo"]), 123.45)
            self.assertIn("google:stale", google["source_status"])
            self.assertEqual(float(meta["speso_effettivo"]), 50)
            metadata = json.loads((root / "data" / "last_update.json").read_text())
            self.assertEqual(metadata["status"], "partial")
            self.assertEqual(metadata["sources"]["google_ads"], "stale")
            self.assertNotIn("secret technical failure", metadata.get("error", ""))

    def test_previous_month_is_never_used_as_fallback(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "report.csv"
            pd.DataFrame(
                [{"row_type": "campaign", "start_date": "2026-06-01"}]
            ).to_csv(path, index=False)
            self.assertEqual(
                report_module._previous_campaign_rows(path, date(2026, 7, 1)), []
            )


if __name__ == "__main__":
    unittest.main()
