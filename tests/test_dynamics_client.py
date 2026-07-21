from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import requests

import src.build_report_data as report_module
from src.build_daily_metrics import build_daily_metrics
from src.build_report_data import build_report_data
from src.dynamics_client import (
    FORMATTED_VALUE,
    DynamicsError,
    DynamicsSettings,
    fetch_effective_leads,
)
from src.validate_dynamics import compare_dynamics_with_export


FETCH_XML = """<fetch><entity name="lead">
<attribute name="leadid"/><attribute name="createdon"/>
<attribute name="campaignid"/><attribute name="new_utmcampaign"/>
<attribute name="emailaddress1"/>
<filter><condition attribute="statecode" operator="eq" value="0"/></filter>
</entity></fetch>"""


def settings(secret: str = "never-print-this") -> DynamicsSettings:
    return DynamicsSettings(
        tenant_id="tenant",
        client_id="client",
        client_secret=secret,
        environment_url="https://example.crm.dynamics.com",
        lead_table="leads",
        lead_view_id="view-id",
        timezone_name="Europe/Rome",
    )


class FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200):
        self.payload = payload
        self.status_code = status_code

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class DynamicsClientTests(unittest.TestCase):
    def test_view_is_minimized_paginated_localized_and_deduplicated(self):
        session = FakeSession(
            [
                FakeResponse({"fetchxml": FETCH_XML, "returnedtypecode": "lead"}),
                FakeResponse(
                    {
                        "value": [
                            {
                                "LogicalName": "campaignid",
                                "DisplayName": {
                                    "LocalizedLabels": [{"Label": "Campagna"}]
                                },
                            },
                            {
                                "LogicalName": "new_utmcampaign",
                                "DisplayName": {
                                    "LocalizedLabels": [{"Label": "Utm campaign"}]
                                },
                            },
                        ]
                    }
                ),
                FakeResponse(
                    {
                        "value": [
                            {
                                "leadid": "L-1",
                                "createdon": "2026-06-30T22:30:00Z",
                                "_campaignid_value": "guid",
                                f"_campaignid_value{FORMATTED_VALUE}": "AREA CLIENTI",
                                "new_utmcampaign": "utm-a",
                            },
                            {
                                "leadid": "L-out",
                                "createdon": "2026-07-20T22:30:00Z",
                                "new_utmcampaign": "outside",
                            },
                        ],
                        "@odata.nextLink": "https://next-page",
                    }
                ),
                FakeResponse(
                    {
                        "value": [
                            {
                                "leadid": "L-1",
                                "createdon": "2026-07-02T10:00:00Z",
                                "new_utmcampaign": "duplicate",
                            },
                            {
                                "leadid": "L-2",
                                "createdon": "2026-07-20T12:00:00Z",
                                "campaignid": "TEXT CAMPAIGN",
                                "new_utmcampaign": "utm-b",
                            },
                        ]
                    }
                ),
            ]
        )

        leads = fetch_effective_leads(
            date(2026, 7, 1),
            date(2026, 7, 20),
            settings=settings(),
            session=session,
            token_provider=lambda _settings: "token",
        )

        self.assertEqual([lead["lead_id"] for lead in leads], ["L-1", "L-2"])
        self.assertEqual(leads[0]["created_at"].hour, 0)
        self.assertEqual(leads[0]["campaign_crm"], "AREA CLIENTI")
        query = session.calls[2][1]["params"]["fetchXml"]
        self.assertNotIn("emailaddress1", query)
        self.assertIn("statecode", query)
        self.assertEqual(session.calls[3][1]["params"], None)

    def test_http_and_network_errors_do_not_expose_secret(self):
        for response in (
            FakeResponse({}, status_code=401),
            requests.Timeout("never-print-this"),
        ):
            with self.subTest(response=type(response).__name__):
                session = FakeSession([response])
                with self.assertRaises(DynamicsError) as caught:
                    fetch_effective_leads(
                        "2026-07-01",
                        "2026-07-20",
                        settings=settings(),
                        session=session,
                        token_provider=lambda _settings: "token",
                        field_names=("campaignid", "new_utmcampaign"),
                    )
                self.assertNotIn("never-print-this", str(caught.exception))


class DynamicsPipelineTests(unittest.TestCase):
    def test_report_uses_api_and_writes_only_hashed_id(self):
        manual = [
            {
                "excel_row": 2,
                "funnel": "Lead Veloce",
                "platform": "Google",
                "channel": "Search",
                "campaign_name": "Plan",
                "investimento_media": 100,
                "stima_lead": 10,
                "cpl_target": 10,
                "google_campaign_id": "g-1",
                "meta_campaign_id": "",
            }
        ]
        mapping = [
            {
                "campaign_plan": "Plan",
                "campaign_crm": "CRM",
                "utm_campaign_1": "utm",
                "utm_campaign_2": "",
                "start_date": "2026-07-01",
                "end_date": "2026-07-31",
            }
        ]
        crm = [
            {
                "lead_id": "original-guid",
                "campaign_crm": "CRM",
                "utm_campaign": "utm",
                "created_at": datetime(2026, 7, 10, 12),
            }
        ]
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with patch.object(report_module, "ROOT", root):
                output = build_report_data(
                    output_path=root / "data/report_data.csv",
                    today=date(2026, 7, 21),
                    manual_fetcher=lambda: manual,
                    mapping_fetcher=lambda: mapping,
                    google_fetcher=lambda _start, _end: [
                        {"campaign_id": "g-1", "campaign_name": "G", "spend": 25}
                    ],
                    meta_fetcher=lambda _start, _end: [],
                    crm_fetcher=lambda _start, _end: crm,
                )
            result = pd.read_csv(output)
            campaign = result[result["row_type"] == "campaign"].iloc[0]
            self.assertEqual(campaign["lead_effettive"], 1)
            audit_text = (root / "data/raw/dynamics_raw.csv").read_text(
                encoding="utf-8-sig"
            )
            self.assertNotIn("original-guid", audit_text)
            self.assertIn("CRM", audit_text)
            metadata = json.loads((root / "data/last_update.json").read_text())
            self.assertEqual(metadata["crm_source"], "dynamics")
            self.assertEqual(metadata["sources"]["crm"], "ok")

    def test_daily_metrics_reuse_pseudonymized_audit_without_second_api_read(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            report = root / "report.csv"
            audit = root / "dynamics_raw.csv"
            output = root / "daily.csv"
            pd.DataFrame([{
                "row_type": "campaign", "start_date": "2026-07-01",
                "end_date": "2026-07-20", "excel_row": "2",
                "campaign_name": "Plan", "platform": "Google",
                "google_campaign_id": "g-1", "meta_campaign_id": "",
                "investimento_media": "100",
            }]).to_csv(report, index=False)
            pd.DataFrame([{
                "lead_id": "hashed-id", "campaign_crm": "CRM",
                "utm_campaign": "utm",
                "created_at": "2026-07-10T00:30:00+02:00",
                "match_status": "matched", "matched_excel_row": "2",
                "lead_allocation_method": "crm_mapping",
            }]).to_csv(audit, index=False)
            with patch.dict("os.environ", {"DYNAMICS_ENABLED": "true"}):
                build_daily_metrics(
                    report_path=report,
                    spend_path=root / "missing-spend.csv",
                    output_path=output,
                    crm_audit_path=audit,
                    manual_fetcher=lambda: [{
                        "excel_row": 2, "campaign_name": "Plan"
                    }],
                    mapping_fetcher=lambda: self.fail(
                        "Il mapping non deve essere riletto in modalità Dynamics."
                    ),
                )
            daily = pd.read_csv(output, dtype=str, keep_default_na=False)
            crm = daily[daily["source"] == "crm"].iloc[0]
            self.assertEqual(crm["date"], "2026-07-10")
            self.assertEqual(crm["leads"], "1")

    def test_validation_requires_exact_allocation_and_status_counts(self):
        with tempfile.TemporaryDirectory() as temp:
            export = Path(temp) / "crm.xlsx"
            pd.DataFrame(
                {
                    "Id Lead": ["L-1"],
                    "Campagna": ["CRM"],
                    "Data e ora di creazione": [datetime(2026, 7, 10, 12)],
                    "Utm campaign": ["utm"],
                }
            ).to_excel(export, sheet_name="LEAD QUESTO MESE PULITE", index=False)
            manual = [{"excel_row": 2, "campaign_name": "Plan", "funnel": "Lead Veloce"}]
            mapping = [{
                "campaign_plan": "Plan", "campaign_crm": "CRM",
                "utm_campaign_1": "utm", "utm_campaign_2": "",
                "start_date": "2026-07-01", "end_date": "2026-07-31",
            }]
            exact, details = compare_dynamics_with_export(
                date(2026, 7, 1), date(2026, 7, 20), export,
                dynamics_fetcher=lambda _start, _end: [{
                    "lead_id": "L-1", "campaign_crm": "CRM",
                    "utm_campaign": "utm", "created_at": datetime(2026, 7, 10, 12),
                }],
                manual_fetcher=lambda: manual,
                mapping_fetcher=lambda: mapping,
            )
            self.assertTrue(exact)
            self.assertEqual(details["api"]["allocations"], {"2": 1})


if __name__ == "__main__":
    unittest.main()
