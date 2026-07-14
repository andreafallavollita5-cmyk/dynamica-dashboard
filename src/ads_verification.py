"""Local-only helpers for visually verifying Ads delivery connections."""

from __future__ import annotations

from collections.abc import Callable

from src.google_ads_client import fetch_google_campaign_delivery
from src.meta_ads_client import fetch_meta_campaign_delivery


DeliveryFetcher = Callable[[str, str], list[dict]]


def fetch_delivery_with_status(
    platform: str,
    fetcher: DeliveryFetcher,
    start_date: str,
    end_date: str,
) -> tuple[list[dict], list[dict], str, str]:
    """Fetch one platform and return delivery, verification rows and safe status."""
    try:
        delivery = fetcher(start_date, end_date)
    except Exception as exc:
        error = str(exc).strip() or f"Collegamento {platform} non riuscito."
        verification = [
            {
                "platform": platform,
                "campaign_id": "",
                "campaign_name": "",
                "periodo_interrogato": f"{start_date} → {end_date}",
                "speso_estratto": None,
                "stato_collegamento": "errore",
                "errore": error,
            }
        ]
        return [], verification, "error", error

    verification = [
        {
            "platform": platform,
            "campaign_id": str(row.get("campaign_id") or ""),
            "campaign_name": str(row.get("campaign_name") or ""),
            "periodo_interrogato": f"{start_date} → {end_date}",
            "speso_estratto": float(row.get("spend") or 0),
            "stato_collegamento": "collegato",
            "errore": "",
        }
        for row in delivery
    ]
    if not verification:
        verification.append(
            {
                "platform": platform,
                "campaign_id": "",
                "campaign_name": "Nessuna campagna con delivery nel periodo",
                "periodo_interrogato": f"{start_date} → {end_date}",
                "speso_estratto": 0.0,
                "stato_collegamento": "collegato",
                "errore": "",
            }
        )
    return delivery, verification, "ok", ""


def verify_ads_connections(
    start_date: str,
    end_date: str,
    google_fetcher: DeliveryFetcher | None = None,
    meta_fetcher: DeliveryFetcher | None = None,
) -> list[dict]:
    """Run real read-only checks for both platforms for the local dashboard."""
    google_fetcher = google_fetcher or fetch_google_campaign_delivery
    meta_fetcher = meta_fetcher or fetch_meta_campaign_delivery
    _, google_verification, _, _ = fetch_delivery_with_status(
        "Google Ads", google_fetcher, start_date, end_date
    )
    _, meta_verification, _, _ = fetch_delivery_with_status(
        "Meta Ads", meta_fetcher, start_date, end_date
    )
    return google_verification + meta_verification
