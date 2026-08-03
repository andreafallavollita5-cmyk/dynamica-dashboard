from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pandas as pd

import app
from src.freeze_monthly_history import (
    backfill_from_archive,
    freeze_completed_month,
)


def write_dataset(
    folder: Path,
    *,
    start: str,
    end: str,
    campaign: str = "Campagna originale",
) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {
                "row_type": "campaign",
                "start_date": start,
                "end_date": end,
                "campaign_name": campaign,
                "investimento_media": 1000,
                "cpl_target": 20,
                "action": "Action congelata",
            }
        ]
    ).to_csv(folder / "report_data.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(
        [
            {
                "date": start,
                "source": "google_ads",
                "excel_row": "2",
                "spend_rollup_excel_row": "2",
                "campaign_id": "123",
                "campaign_name": campaign,
                "spend": 10,
                "leads": "",
                "monthly_lead_target": "",
                "lead_allocation_method": "",
            }
        ]
    ).to_csv(
        folder / "report_daily_metrics.csv", index=False, encoding="utf-8-sig"
    )
    (folder / "last_update.json").write_text(
        json.dumps(
            {
                "client": "Dynamica Retail",
                "start_date": start,
                "end_date": end,
                "status": "ok",
            }
        ),
        encoding="utf-8",
    )


class MonthlyFreezeTests(unittest.TestCase):
    def test_scheduler_freezes_after_archive_and_before_publish(self):
        source = Path("run_daily_update.bat").read_text(encoding="utf-8")
        archive = source.index("-m src.archive_outputs")
        freeze = source.index("-m src.freeze_monthly_history --backfill")
        publish = source.index("-m src.publish_to_github")
        self.assertLess(archive, freeze)
        self.assertLess(freeze, publish)

    def test_only_a_complete_calendar_month_is_frozen(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            partial = root / "partial"
            complete = root / "complete"
            history = root / "history"
            write_dataset(partial, start="2026-07-01", end="2026-07-30")
            write_dataset(complete, start="2026-07-01", end="2026-07-31")

            self.assertIsNone(freeze_completed_month(partial, history))
            destination = freeze_completed_month(complete, history)

            self.assertEqual(destination, history / "2026-07")
            self.assertTrue((destination / "report_data.csv").exists())
            self.assertTrue((destination / "report_daily_metrics.csv").exists())
            self.assertTrue((destination / "last_update.json").exists())

    def test_existing_month_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            history = root / "history"
            write_dataset(
                source,
                start="2026-07-01",
                end="2026-07-31",
                campaign="Versione congelata",
            )
            freeze_completed_month(source, history)
            write_dataset(
                source,
                start="2026-07-01",
                end="2026-07-31",
                campaign="Correzione successiva",
            )

            freeze_completed_month(source, history)

            frozen = pd.read_csv(history / "2026-07" / "report_data.csv")
            self.assertEqual(frozen.iloc[0]["campaign_name"], "Versione congelata")

    def test_unreadable_existing_month_does_not_block_daily_updates(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            history = root / "history"
            destination = history / "2026-07"
            write_dataset(source, start="2026-07-01", end="2026-07-31")
            destination.mkdir(parents=True)

            original_iterdir = Path.iterdir

            def guarded_iterdir(path):
                if path == destination:
                    raise PermissionError("cartella bloccata")
                return original_iterdir(path)

            with patch.object(Path, "iterdir", guarded_iterdir):
                result = freeze_completed_month(source, history)

            self.assertEqual(result, destination)

    def test_backfill_recovers_complete_archives_and_skips_partial_ones(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "archive"
            history = root / "history"
            write_dataset(
                archive / "2026-06-29",
                start="2026-06-01",
                end="2026-06-29",
            )
            write_dataset(
                archive / "2026-06-30",
                start="2026-06-01",
                end="2026-06-30",
            )

            recovered = backfill_from_archive(archive, history)

            self.assertEqual(recovered, [history / "2026-06"])
            self.assertFalse((history / "2026-07").exists())


class DashboardPeriodCatalogTests(unittest.TestCase):
    def test_historical_month_and_latest_month_are_both_resolved(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            latest_data = root / "data" / "report_data.csv"
            latest_daily = root / "data" / "report_daily_metrics.csv"
            latest_metadata = root / "data" / "last_update.json"
            history = root / "data" / "history"
            write_dataset(
                root / "data",
                start="2026-08-01",
                end="2026-08-05",
                campaign="Agosto",
            )
            write_dataset(
                history / "2026-07",
                start="2026-07-01",
                end="2026-07-31",
                campaign="Luglio",
            )
            with (
                patch.object(app, "DATA_PATH", latest_data),
                patch.object(app, "REPORT_DAILY_PATH", latest_daily),
                patch.object(app, "LAST_UPDATE_PATH", latest_metadata),
                patch.object(app, "HISTORY_PATH", history),
            ):
                catalog = app.load_period_catalog()
                july = app.resolve_period_dataset(
                    catalog, date(2026, 7, 10), date(2026, 7, 20)
                )
                august = app.resolve_period_dataset(
                    catalog, date(2026, 8, 1), date(2026, 8, 5)
                )

            self.assertEqual(set(catalog), {"2026-07", "2026-08"})
            self.assertEqual(july["report"], history / "2026-07" / "report_data.csv")
            self.assertEqual(august["report"], latest_data)

    def test_unavailable_month_and_dates_past_latest_are_rejected(self):
        catalog = {
            "2026-08": {
                "start": date(2026, 8, 1),
                "end": date(2026, 8, 5),
            }
        }
        with self.assertRaisesRegex(ValueError, "non è disponibile"):
            app.resolve_period_dataset(
                catalog, date(2026, 7, 1), date(2026, 7, 31)
            )
        with self.assertRaisesRegex(ValueError, "disponibili dati"):
            app.resolve_period_dataset(
                catalog, date(2026, 8, 1), date(2026, 8, 6)
            )


if __name__ == "__main__":
    unittest.main()
