from __future__ import annotations

import unittest
from datetime import date
from unittest.mock import patch

from src.ads_verification import verify_ads_connections
from src.build_report_data import build_report_data, build_report_rows
from src.google_sheets_client import _rows_from_values
from src.google_ads_client import fetch_google_campaign_delivery
from src.google_ads_client import GoogleAdsDeliveryError, _build_client
from src.meta_ads_client import fetch_meta_campaign_delivery


def manual_row(**overrides):
    row = {
        "excel_row": 2, "funnel": "Lead", "platform": "Google Ads",
        "channel": "Search", "campaign_name": "Campagna test",
        "investimento_media": 3100, "percentuale_investimento": 1,
        "cpp_medio": None, "stima_pratiche": None, "cpl_target": 20,
        "stima_lead": 310, "lead_effettive_manual": 10,
        "action": "Manuale", "google_campaign_id": "123",
        "meta_campaign_id": "", "dynamics_campaign_key": "",
    }
    row.update(overrides)
    return row


class AdsReportFlowTests(unittest.TestCase):
    def test_spend_is_joined_by_campaign_id_for_both_platforms(self):
        manual = [
            manual_row(),
            manual_row(excel_row=3, platform="Meta", campaign_name="Meta test",
                       google_campaign_id="", meta_campaign_id="456",
                       lead_effettive_manual=None),
        ]
        google = [{"campaign_id": "123", "campaign_name": "Nome API diverso", "spend": 125.5}]
        meta = [{"campaign_id": "456", "campaign_name": "Meta API", "spend": 88.25}]

        rows = build_report_rows(
            manual, google, meta, date(2026, 7, 1), date(2026, 7, 12),
            report_date=date(2026, 7, 13),
        )

        self.assertEqual(rows[0]["speso_effettivo"], 125.5)
        self.assertEqual(rows[0]["source_status"], "google:ok")
        self.assertEqual(rows[1]["speso_effettivo"], 88.25)
        self.assertEqual(rows[1]["source_status"], "meta:ok")

    def test_effective_leads_come_only_from_manual_input(self):
        google = [{"campaign_id": "123", "campaign_name": "Campagna test",
                   "spend": 100, "conversions": 999}]
        rows = build_report_rows(
            [manual_row(lead_effettive_manual=None)], google, [],
            date(2026, 7, 1), date(2026, 7, 12),
        )
        self.assertIsNone(rows[0]["lead_effettive"])
        self.assertIsNone(rows[0]["cpl_effettivo"])

    def test_api_failure_does_not_turn_unknown_spend_into_zero(self):
        rows = build_report_rows(
            [manual_row()], [], [], date(2026, 7, 1), date(2026, 7, 12),
            google_status="error",
        )
        self.assertIsNone(rows[0]["speso_effettivo"])
        self.assertEqual(rows[0]["source_status"], "google:error")

    def test_name_fallback_is_used_only_when_campaign_id_is_missing(self):
        rows = build_report_rows(
            [manual_row(google_campaign_id="")],
            [{"campaign_id": "999", "campaign_name": "Campagna test", "spend": 42}],
            [], date(2026, 7, 1), date(2026, 7, 12),
        )
        self.assertEqual(rows[0]["speso_effettivo"], 42)
        self.assertEqual(rows[0]["source_status"], "google:ok_name_fallback")

    def test_verification_mock_exposes_required_fields_and_safe_error(self):
        def ok_fetcher(start, end):
            return [{"campaign_id": "123", "campaign_name": "G", "spend": 12.34}]

        def error_fetcher(start, end):
            raise RuntimeError("Collegamento Meta non riuscito.")

        rows = verify_ads_connections(
            "2026-07-01", "2026-07-12", ok_fetcher, error_fetcher
        )
        required = {
            "platform", "campaign_id", "campaign_name", "periodo_interrogato",
            "speso_estratto", "stato_collegamento", "errore",
        }
        self.assertEqual(required, set(rows[0]))
        self.assertEqual(rows[0]["stato_collegamento"], "collegato")
        self.assertEqual(rows[1]["stato_collegamento"], "errore")

    def test_current_visual_sheet_format_is_read_without_total_rows(self):
        values = [
            ["Funnel", "Canale", "Canale", "ID Campagna ", "Campagna",
             "Investimento Media", "%", "CPP medio", "Stima Pratiche",
             "CPL medio", "Stima Lead", "Stima lead giornaliere",
             "Stima lead al 12/7", "Lead effettive", "Delta lead",
             "Speso effettivo al 12/7", "Delta speso", "%Delta delivery",
             "Delta speso", "%Delta delivery", "CPL", "Delta CPL", ""],
            ["Lead Veloce", "Google", "Search", "123", "Campagna G",
             "1.000,00 €", "10%", "", "", "20,00 €", "50", "", "", "7",
             "", "", "", "", "", "", "", "", "Action manuale"],
            ["", "Meta", "Display", "456", "Campagna M", "500,00 €"],
            ["TOT Lead Veloce", "", "", "", "", "1.500,00 €"],
        ]
        rows = _rows_from_values(values)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["google_campaign_id"], "123")
        self.assertEqual(rows[1]["meta_campaign_id"], "456")
        self.assertEqual(rows[1]["funnel"], "Lead Veloce")
        self.assertEqual(rows[0]["action"], "Action manuale")

    def test_google_query_is_read_only_and_excludes_conversions(self):
        captured = {}

        class Service:
            def search_stream(self, customer_id, query):
                captured["query"] = query
                return []

        class Client:
            def get_service(self, name):
                return Service()

        with patch("src.google_ads_client._build_client", return_value=(Client(), "111")):
            self.assertEqual(
                fetch_google_campaign_delivery("2026-07-01", "2026-07-12"), []
            )
        self.assertIn("BETWEEN '2026-07-01' AND '2026-07-12'", captured["query"])
        self.assertNotIn("conversion", captured["query"].lower())

    def test_expired_google_refresh_token_has_a_simple_error(self):
        env = {
            "GOOGLE_ADS_CUSTOMER_ID": "111",
            "GOOGLE_ADS_DEVELOPER_TOKEN": "developer-token",
            "GOOGLE_ADS_REFRESH_TOKEN": "refresh-token",
            "GOOGLE_ADS_CLIENT_SECRETS_PATH": "oauth.json",
        }
        with patch.dict("os.environ", env, clear=False), patch(
            "src.google_ads_client._read_oauth_client",
            return_value=("client-id", "client-secret"),
        ), patch(
            "src.google_ads_client.GoogleAdsClient.load_from_dict",
            side_effect=RuntimeError("invalid_grant: Token has been expired or revoked."),
        ):
            with self.assertRaisesRegex(
                GoogleAdsDeliveryError, "scaduto o revocato"
            ):
                _build_client()

    def test_meta_request_excludes_actions_and_leads(self):
        captured = {}

        def fake_read_all(path, params):
            captured.update(params)
            return []

        env = {
            "META_ACCESS_TOKEN": "test-token",
            "META_AD_ACCOUNT_ID": "123",
            "META_API_VERSION": "v25.0",
        }
        with patch.dict("os.environ", env, clear=False), patch(
            "src.meta_ads_client._read_all", side_effect=fake_read_all
        ):
            self.assertEqual(fetch_meta_campaign_delivery("2026-07-01", "2026-07-12"), [])
        self.assertEqual(
            captured["fields"], "campaign_id,campaign_name,spend,clicks,impressions"
        )
        self.assertNotIn("actions", captured["fields"])
        self.assertNotIn("lead", captured["fields"])

    def test_failed_connections_preserve_existing_latest_csv(self):
        from tempfile import TemporaryDirectory
        from pathlib import Path

        with TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "report.csv"
            output.write_text("previous-latest", encoding="utf-8")

            def fail(start, end):
                raise RuntimeError("API non disponibile")

            with self.assertRaisesRegex(RuntimeError, "file latest precedenti"):
                build_report_data(
                    output_path=output,
                    today=date(2026, 7, 13),
                    manual_fetcher=lambda: [manual_row()],
                    google_fetcher=fail,
                    meta_fetcher=fail,
                )
            self.assertEqual(output.read_text(encoding="utf-8"), "previous-latest")


if __name__ == "__main__":
    unittest.main()
