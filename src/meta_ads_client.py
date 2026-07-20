"""Read-only Meta Ads delivery client used by the daily dashboard flow."""

from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"
GRAPH_HOST = "https://graph.facebook.com"


class MetaAdsDeliveryError(RuntimeError):
    """A safe, user-facing Meta Ads delivery error."""


def _normalize_ad_account_id(value: str | None) -> str:
    cleaned = (value or "").replace(" ", "").strip()
    return cleaned[4:] if cleaned.startswith("act_") else cleaned


def _read_all(path: str, params: dict[str, object]) -> list[dict]:
    url = f"{GRAPH_HOST}/{path.lstrip('/')}?{urlencode(params, doseq=True)}"
    rows: list[dict] = []
    while url:
        request = Request(url, headers={"Accept": "application/json"})
        try:
            with urlopen(request, timeout=60) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            try:
                error = json.loads(
                    exc.read().decode("utf-8", errors="replace")
                ).get("error", {})
            except (OSError, json.JSONDecodeError):
                error = {}
            api_code = error.get("code")
            subcode = error.get("error_subcode")
            api_message = str(error.get("message") or "").casefold()

            if api_code == 190 and (
                subcode in {463, 467} or "expired" in api_message
            ):
                message = "Token Meta Ads scaduto."
            elif api_code == 190:
                message = "Token Meta Ads non valido."
            elif "api access blocked" in api_message:
                message = "App Meta bloccata."
            elif (
                "unsupported get request" in api_message
                or "does not exist" in api_message
                or "cannot be loaded" in api_message
            ):
                message = "Account pubblicitario Meta non accessibile."
            elif api_code == 200 or "permission" in api_message:
                message = "Permessi Meta Ads insufficienti."
            elif exc.code in (401, 403):
                message = "Autenticazione Meta Ads non riuscita."
            elif exc.code == 429:
                message = "Limite temporaneo Meta Ads raggiunto."
            else:
                message = f"Meta Ads ha risposto con errore {exc.code}."
            raise MetaAdsDeliveryError(message) from exc
        except (URLError, TimeoutError) as exc:
            raise MetaAdsDeliveryError("Collegamento a Meta Ads non disponibile.") from exc
        except (OSError, json.JSONDecodeError) as exc:
            raise MetaAdsDeliveryError("Risposta Meta Ads non valida.") from exc

        rows.extend(payload.get("data", []))
        url = str(payload.get("paging", {}).get("next") or "")
    return rows


def fetch_meta_campaign_delivery(start_date: str, end_date: str) -> list[dict]:
    """Return campaign spend/clicks/impressions for an inclusive date range.

    Only delivery fields are requested. In particular, actions and lead metrics
    are excluded so Meta leads can never be used as effective CRM leads.
    """
    load_dotenv(ENV_PATH, encoding="utf-8-sig")
    access_token = os.getenv("META_ACCESS_TOKEN", "").strip()
    ad_account_id = _normalize_ad_account_id(os.getenv("META_AD_ACCOUNT_ID"))
    api_version = os.getenv("META_API_VERSION", "v25.0").strip() or "v25.0"
    missing = [
        name
        for name, value in {
            "META_ACCESS_TOKEN": access_token,
            "META_AD_ACCOUNT_ID": ad_account_id,
        }.items()
        if not value
    ]
    if missing:
        raise MetaAdsDeliveryError(
            "Configurazione Meta Ads incompleta: " + ", ".join(missing)
        )

    path = f"{api_version}/act_{ad_account_id}/insights"
    raw_rows = _read_all(
        path,
        {
            "access_token": access_token,
            "level": "campaign",
            "time_range": json.dumps(
                {"since": start_date, "until": end_date}, separators=(",", ":")
            ),
            "fields": "campaign_id,campaign_name,spend,clicks,impressions",
            "limit": 500,
        },
    )
    return [
        {
            "platform": "Meta Ads",
            "campaign_id": str(row.get("campaign_id") or ""),
            "campaign_name": str(row.get("campaign_name") or "(senza nome campagna)"),
            "start_date": start_date,
            "end_date": end_date,
            "spend": float(row.get("spend") or 0),
            "clicks": int(row.get("clicks") or 0),
            "impressions": int(row.get("impressions") or 0),
        }
        for row in raw_rows
    ]


def fetch_meta_campaign_daily_spend(start_date: str, end_date: str) -> list[dict]:
    """Return one read-only spend row per campaign and date."""
    load_dotenv(ENV_PATH, encoding="utf-8-sig")
    access_token = os.getenv("META_ACCESS_TOKEN", "").strip()
    ad_account_id = _normalize_ad_account_id(os.getenv("META_AD_ACCOUNT_ID"))
    api_version = os.getenv("META_API_VERSION", "v25.0").strip() or "v25.0"
    if not access_token:
        raise MetaAdsDeliveryError("Configurazione Meta Ads incompleta: META_ACCESS_TOKEN")
    if not ad_account_id:
        raise MetaAdsDeliveryError("Configurazione Meta Ads incompleta: META_AD_ACCOUNT_ID")

    raw_rows = _read_all(
        f"{api_version}/act_{ad_account_id}/insights",
        {
            "access_token": access_token,
            "level": "campaign",
            "time_range": json.dumps(
                {"since": start_date, "until": end_date}, separators=(",", ":")
            ),
            "time_increment": 1,
            "fields": "date_start,campaign_id,campaign_name,spend",
            "limit": 500,
        },
    )
    return [
        {
            "date": str(row.get("date_start") or ""),
            "platform": "Meta Ads",
            "campaign_id": str(row.get("campaign_id") or ""),
            "campaign_name": str(row.get("campaign_name") or "(senza nome campagna)"),
            "spend": float(row.get("spend") or 0),
        }
        for row in raw_rows
    ]
