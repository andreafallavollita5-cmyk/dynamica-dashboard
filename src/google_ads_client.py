"""Read-only Google Ads delivery client used by the daily dashboard flow."""

from __future__ import annotations

import json
import os
from pathlib import Path

from dotenv import load_dotenv
from google.ads.googleads.client import GoogleAdsClient
import yaml


ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"


class GoogleAdsDeliveryError(RuntimeError):
    """A safe, user-facing Google Ads delivery error."""


def _normalize_customer_id(value: str | None) -> str:
    return (value or "").replace("-", "").replace(" ", "").strip()


def _read_oauth_client(path_value: str) -> tuple[str, str]:
    path = Path(path_value)
    if not path.is_absolute():
        path = ROOT / path
    if not path.exists():
        raise GoogleAdsDeliveryError("File credenziali Google Ads non trovato.")

    try:
        with path.open("r", encoding="utf-8") as stream:
            payload = json.load(stream)
    except (OSError, json.JSONDecodeError) as exc:
        raise GoogleAdsDeliveryError("File credenziali Google Ads non valido.") from exc

    oauth = payload.get("installed") or payload.get("web") or {}
    client_id = str(oauth.get("client_id") or "").strip()
    client_secret = str(oauth.get("client_secret") or "").strip()
    if not client_id or not client_secret:
        raise GoogleAdsDeliveryError("Credenziali OAuth Google Ads incomplete.")
    return client_id, client_secret


def _read_yaml_config(path_value: str | None) -> dict:
    """Read local Google Ads settings without ever logging their values."""
    path = Path(path_value or "google-ads.yaml")
    if not path.is_absolute():
        path = ROOT / path
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8-sig") as stream:
            payload = yaml.safe_load(stream) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise GoogleAdsDeliveryError("File google-ads.yaml non valido.") from exc
    return payload if isinstance(payload, dict) else {}


def _build_client() -> tuple[GoogleAdsClient, str]:
    load_dotenv(ENV_PATH, encoding="utf-8-sig")
    yaml_config = _read_yaml_config(os.getenv("GOOGLE_ADS_CONFIG_PATH"))
    customer_id = _normalize_customer_id(os.getenv("GOOGLE_ADS_CUSTOMER_ID"))
    developer_token = (
        os.getenv("GOOGLE_ADS_DEVELOPER_TOKEN", "").strip()
        or str(yaml_config.get("developer_token") or "").strip()
    )
    refresh_token = os.getenv("GOOGLE_ADS_REFRESH_TOKEN", "").strip()
    secrets_path = os.getenv("GOOGLE_ADS_CLIENT_SECRETS_PATH", "").strip()

    missing = [
        name
        for name, value in {
            "GOOGLE_ADS_CUSTOMER_ID": customer_id,
            "GOOGLE_ADS_DEVELOPER_TOKEN": developer_token,
            "GOOGLE_ADS_REFRESH_TOKEN": refresh_token,
            "GOOGLE_ADS_CLIENT_SECRETS_PATH": secrets_path,
        }.items()
        if not value
    ]
    if missing:
        raise GoogleAdsDeliveryError(
            "Configurazione Google Ads incompleta: " + ", ".join(missing)
        )

    client_id, client_secret = _read_oauth_client(secrets_path)
    config: dict[str, object] = {
        "developer_token": developer_token,
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "use_proto_plus": True,
    }
    login_customer_id = _normalize_customer_id(
        os.getenv("GOOGLE_ADS_LOGIN_CUSTOMER_ID")
        or str(yaml_config.get("login_customer_id") or "")
    )
    if login_customer_id:
        config["login_customer_id"] = login_customer_id

    try:
        return GoogleAdsClient.load_from_dict(config), customer_id
    except Exception as exc:
        error_message = str(exc).casefold()
        if "invalid_grant" in error_message or "expired or revoked" in error_message:
            safe_message = "Refresh token Google Ads scaduto o revocato."
        elif "developer token" in error_message:
            safe_message = "Developer token Google Ads non valido."
        else:
            safe_message = "Impossibile inizializzare il collegamento Google Ads."
        raise GoogleAdsDeliveryError(safe_message) from exc


def fetch_google_campaign_delivery(start_date: str, end_date: str) -> list[dict]:
    """Return campaign spend/clicks/impressions for an inclusive date range.

    The GAQL query is read-only and deliberately excludes conversion metrics so
    that advertising-platform conversions can never become effective leads.
    """
    client, customer_id = _build_client()
    query = f"""
        SELECT
          campaign.id,
          campaign.name,
          metrics.cost_micros,
          metrics.clicks,
          metrics.impressions
        FROM campaign
        WHERE segments.date BETWEEN '{start_date}' AND '{end_date}'
        ORDER BY metrics.cost_micros DESC
    """

    try:
        service = client.get_service("GoogleAdsService")
        response = service.search_stream(customer_id=customer_id, query=query)
        rows: list[dict] = []
        for batch in response:
            for row in batch.results:
                rows.append(
                    {
                        "platform": "Google Ads",
                        "campaign_id": str(row.campaign.id),
                        "campaign_name": str(row.campaign.name),
                        "start_date": start_date,
                        "end_date": end_date,
                        "spend": int(row.metrics.cost_micros or 0) / 1_000_000,
                        "clicks": int(row.metrics.clicks or 0),
                        "impressions": int(row.metrics.impressions or 0),
                    }
                )
        return rows
    except GoogleAdsDeliveryError:
        raise
    except Exception as exc:
        message = str(exc).lower()
        if "metrics cannot be requested for a manager account" in message:
            safe_message = "GOOGLE_ADS_CUSTOMER_ID indica un account manager, non cliente."
        elif "authentication" in message or "oauth" in message or "token" in message:
            safe_message = "Autenticazione Google Ads non riuscita."
        elif "permission" in message or "authorization" in message:
            safe_message = "Permessi insufficienti per l'account Google Ads."
        else:
            safe_message = "Lettura Google Ads non riuscita."
        raise GoogleAdsDeliveryError(safe_message) from exc


def fetch_google_campaign_daily_spend(start_date: str, end_date: str) -> list[dict]:
    """Return one read-only spend row per campaign and date."""
    client, customer_id = _build_client()
    query = f"""
        SELECT
          segments.date,
          campaign.id,
          campaign.name,
          metrics.cost_micros
        FROM campaign
        WHERE segments.date BETWEEN '{start_date}' AND '{end_date}'
        ORDER BY segments.date, campaign.id
    """
    try:
        service = client.get_service("GoogleAdsService")
        response = service.search_stream(customer_id=customer_id, query=query)
        rows: list[dict] = []
        for batch in response:
            for row in batch.results:
                rows.append(
                    {
                        "date": str(row.segments.date),
                        "platform": "Google Ads",
                        "campaign_id": str(row.campaign.id),
                        "campaign_name": str(row.campaign.name),
                        "spend": int(row.metrics.cost_micros or 0) / 1_000_000,
                    }
                )
        return rows
    except Exception as exc:
        message = str(exc).lower()
        if "authentication" in message or "oauth" in message or "token" in message:
            safe_message = "Autenticazione Google Ads non riuscita."
        elif "permission" in message or "authorization" in message:
            safe_message = "Permessi insufficienti per l'account Google Ads."
        else:
            safe_message = "Lettura giornaliera Google Ads non riuscita."
        raise GoogleAdsDeliveryError(safe_message) from exc
