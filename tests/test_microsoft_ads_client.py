from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.microsoft_ads_client import (
    MicrosoftAdsConfig,
    MicrosoftAdsDeliveryError,
    _oauth_client_secret,
    _parse_spend,
    _read_downloaded_report,
    _read_report,
    load_microsoft_ads_config,
)


class MicrosoftAdsClientTests(unittest.TestCase):
    def test_config_reuses_existing_entra_app_credentials(self):
        env = {
            "MICROSOFT_ADS_DEVELOPER_TOKEN": "developer",
            "MICROSOFT_ADS_ACCOUNT_ID": "180606286",
            "MICROSOFT_ADS_CUSTOMER_ID": "251793731",
            "MICROSOFT_ADS_REFRESH_TOKEN": "refresh",
            "DYNAMICS_CLIENT_ID": "client",
            "DYNAMICS_CLIENT_SECRET": "secret",
            "DYNAMICS_TENANT_ID": "tenant",
        }
        with patch.dict("os.environ", env, clear=True), patch(
            "src.microsoft_ads_client.load_dotenv"
        ):
            config = load_microsoft_ads_config()
        self.assertEqual(config.client_id, "client")
        self.assertEqual(config.client_secret, "secret")
        self.assertEqual(config.tenant_id, "tenant")

    def test_refresh_token_is_required_for_unattended_download(self):
        env = {
            "MICROSOFT_ADS_DEVELOPER_TOKEN": "developer",
            "MICROSOFT_ADS_ACCOUNT_ID": "180606286",
            "MICROSOFT_ADS_CUSTOMER_ID": "251793731",
            "MICROSOFT_ADS_CLIENT_ID": "client",
            "MICROSOFT_ADS_CLIENT_SECRET": "secret",
            "MICROSOFT_ADS_TENANT_ID": "tenant",
            "MICROSOFT_ADS_REFRESH_TOKEN": "",
        }
        with patch.dict("os.environ", env, clear=True), patch(
            "src.microsoft_ads_client.load_dotenv"
        ):
            with self.assertRaisesRegex(
                MicrosoftAdsDeliveryError, "REFRESH_TOKEN"
            ):
                load_microsoft_ads_config()

    def test_public_native_client_never_sends_client_secret(self):
        config = MicrosoftAdsConfig(
            developer_token="developer",
            account_id=180606286,
            customer_id=251793731,
            client_id="client",
            client_secret="dynamics-secret-must-stay-stored",
            tenant_id="tenant",
            refresh_token="refresh",
            redirect_uri="https://login.microsoftonline.com/common/oauth2/nativeclient",
            public_client=True,
        )
        self.assertIsNone(_oauth_client_secret(config))

    def test_report_parser_keeps_only_spend_and_identifiers(self):
        content = (
            "TimePeriod,CampaignId,CampaignName,CurrencyCode,Spend\n"
            "2026-10-01,533498925,DYN_VELOCE Cessione del Quinto,EUR,12.34\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.csv"
            path.write_text(content, encoding="utf-8-sig")
            rows = _read_report(path)
        self.assertEqual(
            rows,
            [{
                "date": "2026-10-01",
                "platform": "Microsoft Ads",
                "campaign_id": "533498925",
                "campaign_name": "DYN_VELOCE Cessione del Quinto",
                "spend": 12.34,
            }],
        )

    def test_non_eur_report_is_rejected(self):
        content = (
            "TimePeriod,CampaignId,CampaignName,CurrencyCode,Spend\n"
            "2026-10-01,533498925,Campaign,USD,12.34\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.csv"
            path.write_text(content, encoding="utf-8-sig")
            with self.assertRaisesRegex(MicrosoftAdsDeliveryError, "EUR"):
                _read_report(path)

    def test_decimal_comma_spend_is_supported(self):
        self.assertEqual(_parse_spend("12,34"), 12.34)

    def test_missing_download_means_no_spend_in_period(self):
        self.assertEqual(_read_downloaded_report(None), [])


if __name__ == "__main__":
    unittest.main()
