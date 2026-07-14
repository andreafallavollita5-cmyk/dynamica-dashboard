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


def load_meta_settings() -> dict[str, str]:
    load_dotenv(ENV_PATH, encoding="utf-8-sig")
    return {
        "app_id": os.getenv("META_APP_ID", "").strip(),
        "access_token": os.getenv("META_ACCESS_TOKEN", "").strip(),
        "ad_account_id": normalize_ad_account_id(
            os.getenv("META_AD_ACCOUNT_ID", "").strip()
        ),
        "api_version": os.getenv("META_API_VERSION", "v25.0").strip() or "v25.0",
        "db_path": os.getenv("GOOGLE_ADS_DB_PATH", "data/google_ads.db").strip(),
    }


def normalize_ad_account_id(ad_account_id: str) -> str:
    cleaned = ad_account_id.strip().replace(" ", "")
    return cleaned[4:] if cleaned.startswith("act_") else cleaned


def graph_get(path: str, params: dict[str, object]) -> dict:
    query = urlencode(params, doseq=True)
    url = f"{GRAPH_HOST}/{path.lstrip('/')}?{query}"
    request = Request(url, headers={"Accept": "application/json"})
    try:
        with urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Meta API error {exc.code}: {body}") from exc
    except URLError as exc:
        raise RuntimeError(f"Meta API connection error: {exc.reason}") from exc


def graph_get_all(path: str, params: dict[str, object]) -> list[dict]:
    payload = graph_get(path, params)
    data = list(payload.get("data", []))

    while payload.get("paging", {}).get("next"):
        request = Request(payload["paging"]["next"], headers={"Accept": "application/json"})
        try:
            with urlopen(request, timeout=60) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Meta API error {exc.code}: {body}") from exc
        except URLError as exc:
            raise RuntimeError(f"Meta API connection error: {exc.reason}") from exc
        data.extend(payload.get("data", []))

    return data


def resolve_db_path(db_path: str) -> Path:
    path = Path(db_path)
    if not path.is_absolute():
        path = ROOT / path
    return path
