from __future__ import annotations

import json
import os
from pathlib import Path

from dotenv import load_dotenv
from google.ads.googleads.client import GoogleAdsClient


ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"


def load_settings() -> dict[str, str]:
    load_dotenv(ENV_PATH, encoding="utf-8-sig")
    return {
        "developer_token": os.getenv("GOOGLE_ADS_DEVELOPER_TOKEN", "").strip(),
        "client_secrets_path": os.getenv("GOOGLE_ADS_CLIENT_SECRETS_PATH", "").strip(),
        "refresh_token": os.getenv("GOOGLE_ADS_REFRESH_TOKEN", "").strip(),
        "login_customer_id": normalize_customer_id(
            os.getenv("GOOGLE_ADS_LOGIN_CUSTOMER_ID", "").strip()
        ),
        "customer_id": normalize_customer_id(
            os.getenv("GOOGLE_ADS_CUSTOMER_ID", "").strip()
        ),
        "db_path": os.getenv("GOOGLE_ADS_DB_PATH", "data/google_ads.db").strip(),
    }


def normalize_customer_id(customer_id: str | None) -> str:
    return (customer_id or "").replace("-", "").replace(" ", "")


def read_oauth_client(client_secrets_path: str) -> tuple[str, str]:
    if not client_secrets_path:
        raise RuntimeError("GOOGLE_ADS_CLIENT_SECRETS_PATH is missing in .env")

    with open(client_secrets_path, "r", encoding="utf-8") as f:
        payload = json.load(f)

    client = payload.get("installed") or payload.get("web") or {}
    client_id = client.get("client_id")
    client_secret = client.get("client_secret")
    if not client_id or not client_secret:
        raise RuntimeError("Client secret JSON does not contain client_id/client_secret")

    return client_id, client_secret


def google_ads_client(
    *,
    login_customer_id: str | None = None,
) -> GoogleAdsClient:
    settings = load_settings()
    client_id, client_secret = read_oauth_client(settings["client_secrets_path"])

    missing = [
        name
        for name, value in {
            "GOOGLE_ADS_DEVELOPER_TOKEN": settings["developer_token"],
            "GOOGLE_ADS_REFRESH_TOKEN": settings["refresh_token"],
        }.items()
        if not value
    ]
    if missing:
        raise RuntimeError(f"Missing required setting(s): {', '.join(missing)}")

    config = {
        "developer_token": settings["developer_token"],
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": settings["refresh_token"],
        "use_proto_plus": True,
    }

    login_id = normalize_customer_id(login_customer_id) or settings["login_customer_id"]
    if login_id:
        config["login_customer_id"] = login_id

    return GoogleAdsClient.load_from_dict(config)
