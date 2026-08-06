from __future__ import annotations

import unittest

import pandas as pd

from app import build_campaign_table_html
from src.combined_campaigns import apply_combined_campaign_metrics


class CampaignIndependenceTests(unittest.TestCase):
    def test_metrics_are_not_combined_by_adjacent_excel_rows(self):
        rows = [
            {
                "excel_row": 9,
                "stima_lead": 234,
                "stima_lead_giornaliere": 7.5,
                "stima_lead_progressiva": 128,
                "lead_effettive": 61,
                "speso_effettivo": 5490,
                "cpl_target": 38.5,
                "delta_lead": 67,
                "cpl_effettivo": 5490 / 61,
                "delta_cpl": 5490 / 61 - 38.5,
                "source_status": "google:ok",
            },
            {
                "excel_row": 10,
                "stima_lead": None,
                "stima_lead_giornaliere": None,
                "stima_lead_progressiva": None,
                "lead_effettive": 92,
                "speso_effettivo": None,
                "cpl_target": None,
                "delta_lead": None,
                "cpl_effettivo": None,
                "delta_cpl": None,
                "source_status": "google:rolled_up_to_excel_row_9",
            },
        ]

        result = apply_combined_campaign_metrics(rows)

        self.assertEqual(result[0]["stima_lead_progressiva"], 128)
        self.assertEqual(result[0]["lead_effettive"], 61)
        self.assertEqual(result[1]["lead_effettive"], 92)
        self.assertEqual(result[0]["delta_lead"], 67)
        self.assertIsNone(result[1]["delta_lead"])
        self.assertAlmostEqual(result[0]["cpl_effettivo"], 5490 / 61)
        self.assertAlmostEqual(result[0]["delta_cpl"], 5490 / 61 - 38.5)
        self.assertIsNone(result[1]["cpl_effettivo"])

    def test_dashboard_keeps_every_campaign_value_visible(self):
        display = pd.DataFrame(
            [
                {
                    "Campagna": "Legacy",
                    "Stima Lead": "128",
                    "Lead Effettive": "61",
                    "Delta Lead": "+25",
                    "CPL Effettivo": "35,88 EUR",
                    "Delta CPL": "-2,62 EUR",
                },
                {
                    "Campagna": "Nuova",
                    "Stima Lead": "-",
                    "Lead Effettive": "92",
                    "Delta Lead": "-",
                    "CPL Effettivo": "-",
                    "Delta CPL": "-",
                },
            ]
        )

        rendered = build_campaign_table_html(
            display, ["campaign", "campaign"], [9, 10]
        )

        self.assertNotIn('rowspan="2"', rendered)
        self.assertIn(">61</td>", rendered)
        self.assertIn(">92</td>", rendered)
        self.assertEqual(rendered.count("col-stima-lead"), 3)
        self.assertEqual(rendered.count(">128</td>"), 1)
        self.assertIn('<td class="col-metric col-stima-lead">-</td>', rendered)


if __name__ == "__main__":
    unittest.main()
