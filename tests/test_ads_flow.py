from __future__ import annotations

import unittest
from datetime import date
from unittest.mock import patch

import pandas as pd

from app import calculate_cpl_efficiency, calculate_dashboard_metrics
from src.ads_verification import verify_ads_connections
from src.build_report_data import build_report_data, build_report_rows
from src.google_sheets_client import _is_enabled, _rows_from_values
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
    def test_cpl_efficiency_has_the_correct_sign(self):
        self.assertAlmostEqual(calculate_cpl_efficiency(20.44, 20.0), -0.022)
        self.assertAlmostEqual(calculate_cpl_efficiency(19.0, 20.0), 0.05)
        self.assertEqual(calculate_cpl_efficiency(20.0, 20.0), 0.0)
        self.assertIsNone(calculate_cpl_efficiency(None, 20.0))

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
             "1.000,00 €", "10%", "", "", "20,00 €", "50", "1,61", "19,35", "7",
             "-12,35", "32,26", "387,10", "420,00", "32,90", "8,5%", "60,00", "40,00", "Action manuale"],
            ["", "", "", "124", "Campagna G nuova"],
            ["", "Meta", "Display", "456", "Campagna M", "500,00 €"],
            ["TOT Lead Veloce", "", "", "", "", "1.500,00 €"],
        ]
        rows = _rows_from_values(values)
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["google_campaign_id"], "123")
        self.assertEqual(rows[1]["google_campaign_id"], "124")
        self.assertEqual(rows[1]["platform"], "Google")
        self.assertEqual(rows[1]["channel"], "Search")
        self.assertEqual(rows[2]["meta_campaign_id"], "456")
        self.assertEqual(rows[2]["funnel"], "Lead Veloce")
        self.assertEqual(rows[0]["action"], "Action manuale")
        self.assertEqual(rows[0]["stima_lead_giornaliere"], 1.61)
        self.assertEqual(rows[0]["stima_lead_progressiva"], 19.35)
        self.assertEqual(rows[0]["delta_lead"], -12.35)
        self.assertEqual(rows[0]["stima_spending_progressiva"], 387.1)
        self.assertEqual(rows[0]["speso_effettivo_manual"], 420)

    def test_legacy_sheet_marks_ads_campaign_without_id_inactive(self):
        values = [
            ["Funnel", "Canale", "Canale", "ID Campagna", "Campagna",
             "Investimento Media", "%", "CPP medio", "Stima Pratiche",
             "CPL medio", "Stima Lead", "Stima lead giornaliere",
             "Stima lead al 12/07", "Lead effettive", "Delta lead",
             "Stima spesa giornaliero", "Stima spending al 12/07",
             "Speso effettivo 12/07", "Delta speso", "%Delta delivery",
             "CPL", "Delta CPL", "Action"],
            ["Lead Veloce", "Meta", "Display", "",
             "DYN_VELOCE LeadGen DIP - CQD | CBO Scaling (F3)"],
        ]
        rows = _rows_from_values(values)
        self.assertEqual(len(rows), 1)
        self.assertFalse(_is_enabled(rows[0]))

    def test_legacy_sheet_extracts_official_totals_and_area_subtotal(self):
        values = [
            ["Funnel", "Canale", "Canale", "ID Campagna", "Campagna",
             "Investimento Media", "%", "CPP medio", "Stima Pratiche",
             "CPL medio", "Stima Lead", "Stima lead giornaliere",
             "Stima lead al 12/07", "Lead effettive", "Delta lead",
             "Stima spesa giornaliero", "Stima spending al 12/07",
             "Speso effettivo 12/07", "Delta speso", "%Delta delivery",
             "CPL", "Delta CPL", "Action"],
            ["Area Clienti", "Google", "Search", "123", "Campaign", 1000],
            ["TOT Area Clienti", "", "", "", "", 1000, 0.5, "", "", "",
             "", "", 180.6451612903226, 215],
            ["TOT Lead Veloce", "", "", "", "", 31000, 0.49206349,
             560.0167, 55.3554, 22.682, 1366.718, 44.087, 529.052, 599],
            ["TOT DEM", "", "", "", "", 11000, 0.17460317,
             376.6304, 29.2063, 8.134, 1352.339, 58.797, 470.378, 524],
            ["", "", "", "", "", 63000, 1, 468.18, 135, 19.775722922,
             3185.72, 117.93, 1180.0762901691826, 1338, -157.92, 2032.25,
             24387.09677419355, 27880.83, 3493.733225806449, 0.1432615476,
             20.83769058, 1.06196766],
        ]
        rows = _rows_from_values(values)
        self.assertEqual(rows[0]["sheet_total_investimento_media"], 63000)
        self.assertAlmostEqual(
            rows[0]["sheet_total_stima_spending_progressiva"], 24387.09677419355
        )
        self.assertEqual(rows[0]["sheet_total_lead_effettive"], 1338)
        self.assertAlmostEqual(
            rows[0]["sheet_area_clienti_stima_lead_progressiva_subtotal"],
            180.6451612903226,
        )
        self.assertEqual(
            rows[0]["sheet_area_clienti_lead_effettive_subtotal"], 215
        )
        self.assertEqual(
            rows[0]["sheet_lead_veloce_investimento_media_subtotal"], 31000
        )
        self.assertEqual(rows[0]["sheet_dem_lead_effettive_subtotal"], 524)

    def test_legacy_sheet_formulas_and_manual_non_ads_spend_are_preserved(self):
        manual = manual_row(
            platform="Dem",
            channel="DEM",
            google_campaign_id="",
            investimento_media=5000,
            stima_lead=657.8947368421053,
            stima_lead_giornaliere=28.604118993135014,
            stima_lead_progressiva=228.8329519450801,
            lead_effettive_manual=239,
            delta_lead=10.167048054919889,
            stima_spending_progressiva=1739.1304347826087,
            speso_effettivo_manual=1816.4,
            cpl_target=7.6,
        )
        rows = build_report_rows(
            [manual], [], [], date(2026, 7, 1), date(2026, 7, 12)
        )
        self.assertAlmostEqual(rows[0]["stima_lead_progressiva"], 228.8329519450801)
        self.assertAlmostEqual(rows[0]["delta_lead"], 10.167048054919889)
        self.assertAlmostEqual(rows[0]["stima_spending_progressiva"], 1739.1304347826087)
        self.assertAlmostEqual(rows[0]["speso_effettivo"], 1816.4)
        self.assertAlmostEqual(rows[0]["cpl_effettivo"], 7.6)
        self.assertEqual(rows[0]["source_status"], "manual:sheet_spend")

    def test_delta_lead_is_effective_minus_estimated(self):
        rows = build_report_rows(
            [
                manual_row(
                    stima_lead_progressiva=70,
                    lead_effettive_manual=80,
                    sheet_total_lead_effettive=80,
                    sheet_total_stima_lead_progressiva=70,
                )
            ],
            [{"campaign_id": "123", "campaign_name": "Campagna test", "spend": 10}],
            [],
            date(2026, 7, 1),
            date(2026, 7, 12),
        )
        self.assertEqual(rows[0]["delta_lead"], 10)
        self.assertEqual(rows[0]["kpi_delta_lead_totale"], 10)

    def test_ads_spend_overrides_legacy_manual_spend(self):
        rows = build_report_rows(
            [manual_row(speso_effettivo_manual=999)],
            [{"campaign_id": "123", "campaign_name": "Campagna test", "spend": 12.5}],
            [],
            date(2026, 7, 1),
            date(2026, 7, 12),
        )
        self.assertEqual(rows[0]["speso_effettivo"], 12.5)

    def test_legacy_continuation_campaign_spend_rolls_up_to_budgeted_parent(self):
        manual = [
            manual_row(excel_row=2, investimento_media=1000, lead_effettive_manual=10),
            manual_row(
                excel_row=3,
                campaign_name="Campagna test child",
                google_campaign_id="124",
                investimento_media=None,
                lead_effettive_manual=None,
            ),
        ]
        google = [
            {"campaign_id": "123", "campaign_name": "Parent API", "spend": 100},
            {"campaign_id": "124", "campaign_name": "Child API", "spend": 40},
        ]
        rows = build_report_rows(
            manual, google, [], date(2026, 7, 1), date(2026, 7, 12)
        )
        self.assertEqual(rows[0]["speso_effettivo"], 140)
        self.assertIsNone(rows[1]["speso_effettivo"])
        self.assertIn("google:includes_excel_row_3", rows[0]["source_status"])
        self.assertEqual(rows[1]["source_status"], "google:rolled_up_to_excel_row_2")

    def test_official_kpi_totals_are_separate_from_campaign_values(self):
        manual = [
            manual_row(
                funnel="Area Clienti",
                investimento_media=1000,
                stima_lead_progressiva=10,
                lead_effettive_manual=20,
                stima_spending_progressiva=100,
                sheet_total_investimento_media=63000,
                sheet_total_stima_spending_progressiva=24387.09677419355,
                sheet_total_lead_effettive=1338,
                sheet_total_stima_lead_progressiva=1180.0762901691826,
                sheet_total_cpl_target=19.77572292204534,
                sheet_area_clienti_lead_effettive_subtotal=215,
                sheet_area_clienti_stima_lead_progressiva_subtotal=180.6451612903226,
                sheet_area_clienti_investimento_media_subtotal=21000,
                sheet_area_clienti_cpl_target_subtotal=45,
            )
        ]
        rows = build_report_rows(
            manual,
            [{"campaign_id": "123", "campaign_name": "Campaign", "spend": 200}],
            [],
            date(2026, 7, 1),
            date(2026, 7, 12),
        )
        self.assertEqual(rows[0]["lead_effettive"], 20)
        self.assertEqual(rows[0]["kpi_lead_effettive_totale"], 1338)
        self.assertEqual(rows[0]["kpi_investimento_media_totale"], 63000)
        self.assertAlmostEqual(
            rows[0]["kpi_stima_spending_progressiva_totale"], 24387.09677419355
        )
        self.assertEqual(rows[0]["sheet_area_clienti_lead_effettive_subtotal"], 215)
        self.assertEqual(rows[0]["subtotal_area_clienti_investimento_media"], 21000)
        self.assertAlmostEqual(rows[0]["subtotal_area_clienti_speso_effettivo"], 200)
        self.assertAlmostEqual(rows[0]["subtotal_area_clienti_cpl_effettivo"], 200 / 215)

    def test_dashboard_uses_official_totals_only_for_full_scope(self):
        frame = pd.DataFrame(
            [{
                "investimento_media": 1000,
                "stima_spending_progressiva": 100,
                "speso_effettivo": 200,
                "lead_effettive": 20,
                "stima_lead_progressiva": 10,
                "cpl_target": 5,
                "kpi_investimento_media_totale": 63000,
                "kpi_stima_spending_progressiva_totale": 24387.09677419355,
                "kpi_speso_effettivo_totale": 27882.13,
                "kpi_lead_effettive_totale": 1338,
                "kpi_stima_lead_progressiva_totale": 1180.0762901691826,
                "kpi_cpl_target_totale": 19.77572292204534,
            }]
        )
        filtered = calculate_dashboard_metrics(frame, use_official_totals=False)
        official = calculate_dashboard_metrics(frame, use_official_totals=True)
        self.assertEqual(filtered["lead_total"], 20)
        self.assertEqual(official["lead_total"], 1338)
        self.assertEqual(official["budget_total"], 63000)
        self.assertAlmostEqual(official["planned_spend"], 24387.09677419355)

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
