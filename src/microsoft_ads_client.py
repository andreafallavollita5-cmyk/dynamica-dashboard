"""Read Microsoft Advertising campaign spend without changing Ads data."""

from __future__ import annotations

import csv
import os
import tempfile
import time
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Callable

from dotenv import load_dotenv, set_key


ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"
ROME_REPORT_TIME_ZONE = "AmsterdamBerlinBernRomeStockholmVienna"


class MicrosoftAdsDeliveryError(RuntimeError):
    """Raised when Microsoft Ads cannot return a safe spend report."""


@dataclass(frozen=True)
class MicrosoftAdsConfig:
    developer_token: str
    account_id: int
    customer_id: int
    client_id: str
    client_secret: str
    tenant_id: str
    refresh_token: str
    redirect_uri: str
    environment: str = "production"
    public_client: bool = False


def _env(name: str, fallback: str = "") -> str:
    return (os.getenv(name) or os.getenv(fallback) or "").strip()


def _env_bool(name: str, default: bool = False) -> bool:
    value = _env(name).lower()
    if not value:
        return default
    return value in {"1", "true", "yes", "on"}


def load_microsoft_ads_config(*, require_refresh_token: bool = True) -> MicrosoftAdsConfig:
    """Load Ads credentials, reusing the existing Entra app when configured."""
    load_dotenv(ENV_PATH, encoding="utf-8-sig")
    values = {
        "developer_token": _env("MICROSOFT_ADS_DEVELOPER_TOKEN"),
        "account_id": _env("MICROSOFT_ADS_ACCOUNT_ID"),
        "customer_id": _env("MICROSOFT_ADS_CUSTOMER_ID"),
        "client_id": _env("MICROSOFT_ADS_CLIENT_ID", "DYNAMICS_CLIENT_ID"),
        "client_secret": _env(
            "MICROSOFT_ADS_CLIENT_SECRET", "DYNAMICS_CLIENT_SECRET"
        ),
        "tenant_id": _env("MICROSOFT_ADS_TENANT_ID", "DYNAMICS_TENANT_ID"),
        "refresh_token": _env("MICROSOFT_ADS_REFRESH_TOKEN"),
        "redirect_uri": _env("MICROSOFT_ADS_REDIRECT_URI"),
    }
    required = [
        "developer_token", "account_id", "customer_id", "client_id",
        "tenant_id",
    ]
    if require_refresh_token:
        required.append("refresh_token")
    missing = [name for name in required if not values[name]]
    if missing:
        friendly = ", ".join(f"MICROSOFT_ADS_{name.upper()}" for name in missing)
        raise MicrosoftAdsDeliveryError(
            "Configurazione Microsoft Ads incompleta: " + friendly + "."
        )
    if not values["redirect_uri"]:
        values["redirect_uri"] = "http://localhost/callback"
    try:
        account_id = int(values["account_id"])
        customer_id = int(values["customer_id"])
    except ValueError as exc:
        raise MicrosoftAdsDeliveryError(
            "Account ID o Customer ID Microsoft Ads non valido."
        ) from exc
    return MicrosoftAdsConfig(
        developer_token=values["developer_token"],
        account_id=account_id,
        customer_id=customer_id,
        client_id=values["client_id"],
        client_secret=values["client_secret"],
        tenant_id=values["tenant_id"],
        refresh_token=values["refresh_token"],
        redirect_uri=values["redirect_uri"],
        environment=_env("MICROSOFT_ADS_ENVIRONMENT") or "production",
        public_client=_env_bool("MICROSOFT_ADS_PUBLIC_CLIENT"),
    )


def _oauth_client_secret(config: MicrosoftAdsConfig) -> str | None:
    """Public/native Entra applications must not send a client secret."""
    return None if config.public_client else config.client_secret


def _save_rotated_refresh_token(tokens: object) -> None:
    """Persist Microsoft's latest refresh token without logging it."""
    refresh_token = str(getattr(tokens, "refresh_token", "") or "").strip()
    if not refresh_token:
        return
    if not ENV_PATH.exists():
        raise MicrosoftAdsDeliveryError("File .env non trovato.")
    set_key(str(ENV_PATH), "MICROSOFT_ADS_REFRESH_TOKEN", refresh_token, quote_mode="always")


def _authorization_data(config: MicrosoftAdsConfig):
    try:
        from bingads.authorization import AuthorizationData, OAuthWebAuthCodeGrant
    except ImportError as exc:
        raise MicrosoftAdsDeliveryError(
            "Libreria bingads non installata. Eseguire pip install -r requirements.txt."
        ) from exc

    oauth = OAuthWebAuthCodeGrant(
        client_id=config.client_id,
        client_secret=_oauth_client_secret(config),
        redirection_uri=config.redirect_uri,
        token_refreshed_callback=_save_rotated_refresh_token,
        env=config.environment,
        tenant=config.tenant_id,
    )
    try:
        oauth.request_oauth_tokens_by_refresh_token(config.refresh_token)
    except Exception as exc:
        raise MicrosoftAdsDeliveryError(
            "Autorizzazione Microsoft Ads non valida o scaduta; rigenerare il refresh token."
        ) from exc
    return AuthorizationData(
        account_id=config.account_id,
        customer_id=config.customer_id,
        developer_token=config.developer_token,
        authentication=oauth,
    )


def build_authorization_url() -> str:
    """Return the one-time Microsoft consent URL for the configured Entra app."""
    config = load_microsoft_ads_config(require_refresh_token=False)
    if not _env("MICROSOFT_ADS_REDIRECT_URI"):
        raise MicrosoftAdsDeliveryError(
            "Configurare MICROSOFT_ADS_REDIRECT_URI con un URI registrato nell'app Entra."
        )
    from bingads.authorization import OAuthWebAuthCodeGrant

    oauth = OAuthWebAuthCodeGrant(
        client_id=config.client_id,
        client_secret=_oauth_client_secret(config),
        redirection_uri=config.redirect_uri,
        token_refreshed_callback=_save_rotated_refresh_token,
        env=config.environment,
        tenant=config.tenant_id,
    )
    return oauth.get_authorization_endpoint()


def exchange_authorization_response(response_uri: str) -> None:
    """Exchange the browser callback for tokens and store only the refresh token."""
    config = load_microsoft_ads_config(require_refresh_token=False)
    if not _env("MICROSOFT_ADS_REDIRECT_URI"):
        raise MicrosoftAdsDeliveryError(
            "Configurare MICROSOFT_ADS_REDIRECT_URI con un URI registrato nell'app Entra."
        )
    from bingads.authorization import OAuthWebAuthCodeGrant

    oauth = OAuthWebAuthCodeGrant(
        client_id=config.client_id,
        client_secret=_oauth_client_secret(config),
        redirection_uri=config.redirect_uri,
        token_refreshed_callback=_save_rotated_refresh_token,
        env=config.environment,
        tenant=config.tenant_id,
    )
    try:
        oauth.request_oauth_tokens_by_response_uri(response_uri.strip())
    except Exception as exc:
        raise MicrosoftAdsDeliveryError(
            "Il consenso Microsoft Ads non è stato completato correttamente."
        ) from exc


def authorize_with_device_code() -> None:
    """Authorize without relying on the transient native callback."""
    config = load_microsoft_ads_config(require_refresh_token=False)
    if not config.public_client and not config.client_secret:
        raise MicrosoftAdsDeliveryError(
            "Il flusso codice dispositivo richiede il client secret configurato."
        )

    import requests

    authority = f"https://login.microsoftonline.com/{config.tenant_id}/oauth2/v2.0"
    scope = "https://ads.microsoft.com/msads.manage offline_access"
    try:
        response = requests.post(
            f"{authority}/devicecode",
            data={"client_id": config.client_id, "scope": scope},
            timeout=30,
        )
        response.raise_for_status()
        device = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise MicrosoftAdsDeliveryError(
            "Avvio autorizzazione Microsoft Ads non riuscito."
        ) from exc

    verification_uri = str(device.get("verification_uri") or "").strip()
    user_code = str(device.get("user_code") or "").strip()
    device_code = str(device.get("device_code") or "").strip()
    if not verification_uri or not user_code or not device_code:
        raise MicrosoftAdsDeliveryError(
            "Microsoft non ha restituito un codice dispositivo valido."
        )

    print(f"Apri {verification_uri} e inserisci il codice: {user_code}")
    print("In attesa del completamento dell'accesso Microsoft...")
    interval = max(int(device.get("interval") or 5), 1)
    expires_at = time.monotonic() + max(int(device.get("expires_in") or 900), 60)
    token_url = f"{authority}/token"
    while time.monotonic() < expires_at:
        time.sleep(interval)
        try:
            token_data = {
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "client_id": config.client_id,
                "device_code": device_code,
            }
            if not config.public_client:
                token_data["client_secret"] = config.client_secret
            token_response = requests.post(
                token_url,
                data=token_data,
                timeout=30,
            )
            payload = token_response.json()
        except (requests.RequestException, ValueError) as exc:
            raise MicrosoftAdsDeliveryError(
                "Completamento autorizzazione Microsoft Ads non riuscito."
            ) from exc

        if token_response.ok:
            refresh_token = str(payload.get("refresh_token") or "").strip()
            if not refresh_token:
                raise MicrosoftAdsDeliveryError(
                    "Microsoft non ha restituito il refresh token richiesto."
                )
            if not ENV_PATH.exists():
                raise MicrosoftAdsDeliveryError("File .env non trovato.")
            set_key(
                str(ENV_PATH),
                "MICROSOFT_ADS_REFRESH_TOKEN",
                refresh_token,
                quote_mode="always",
            )
            return

        error = str(payload.get("error") or "").strip()
        if error == "authorization_pending":
            continue
        if error == "slow_down":
            interval += 5
            continue
        if error in {"authorization_declined", "expired_token", "bad_verification_code"}:
            raise MicrosoftAdsDeliveryError(
                "Autorizzazione Microsoft Ads annullata o scaduta."
            )
        error_description = str(payload.get("error_description") or "").strip()
        aad_code = ""
        if "AADSTS" in error_description:
            aad_code = error_description[error_description.index("AADSTS"):].split(":", 1)[0]
        detail = "/".join(part for part in (error, aad_code) if part)
        raise MicrosoftAdsDeliveryError(
            "Microsoft ha rifiutato l'autorizzazione Ads"
            + (f" ({detail})." if detail else ".")
        )

    raise MicrosoftAdsDeliveryError("Codice dispositivo Microsoft Ads scaduto.")


def _report_date(factory: object, value: date) -> object:
    result = factory.create("Date")
    result.Day = value.day
    result.Month = value.month
    result.Year = value.year
    return result


def _build_report_request(manager: object, config: MicrosoftAdsConfig, start: date, end: date):
    factory = manager.service_client.factory
    request = factory.create("CampaignPerformanceReportRequest")
    request.Format = "Csv"
    request.FormatVersion = "2.0"
    request.ReportName = "Dynamica Microsoft Ads spend"
    request.ReturnOnlyCompleteData = False
    request.Aggregation = "Daily"
    request.ExcludeReportHeader = True
    request.ExcludeReportFooter = True
    request.ExcludeColumnHeaders = False

    scope = factory.create("AccountThroughCampaignReportScope")
    scope.AccountIds = {"long": [config.account_id]}
    scope.Campaigns = None
    request.Scope = scope

    report_time = factory.create("ReportTime")
    report_time.CustomDateRangeStart = _report_date(factory, start)
    report_time.CustomDateRangeEnd = _report_date(factory, end)
    report_time.PredefinedTime = None
    report_time.ReportTimeZone = ROME_REPORT_TIME_ZONE
    request.Time = report_time

    columns = factory.create("ArrayOfCampaignPerformanceReportColumn")
    columns.CampaignPerformanceReportColumn.append(
        ["TimePeriod", "CampaignId", "CampaignName", "CurrencyCode", "Spend"]
    )
    request.Columns = columns
    return request


def _parse_date(value: str) -> str:
    text = value.strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    raise MicrosoftAdsDeliveryError("Microsoft Ads ha restituito una data non valida.")


def _parse_spend(value: str) -> float:
    text = value.strip().replace("\u00a0", "").replace(" ", "")
    if "," in text and "." in text:
        text = text.replace(",", "")
    elif "," in text:
        text = text.replace(",", ".")
    try:
        return float(text or 0)
    except ValueError as exc:
        raise MicrosoftAdsDeliveryError(
            "Microsoft Ads ha restituito uno spend non numerico."
        ) from exc


def _read_report(path: Path) -> list[dict]:
    rows: list[dict] = []
    try:
        with path.open("r", newline="", encoding="utf-8-sig") as stream:
            for item in csv.DictReader(stream):
                campaign_id = str(item.get("CampaignId") or "").strip()
                if not campaign_id:
                    continue
                currency = str(item.get("CurrencyCode") or "").strip().upper()
                if currency and currency != "EUR":
                    raise MicrosoftAdsDeliveryError(
                        "L'account Microsoft Ads non sta rendicontando in EUR."
                    )
                rows.append(
                    {
                        "date": _parse_date(str(item.get("TimePeriod") or "")),
                        "platform": "Microsoft Ads",
                        "campaign_id": campaign_id,
                        "campaign_name": str(item.get("CampaignName") or "").strip(),
                        "spend": _parse_spend(str(item.get("Spend") or "0")),
                    }
                )
    except OSError as exc:
        raise MicrosoftAdsDeliveryError(
            "Report Microsoft Ads non leggibile."
        ) from exc
    return rows


def _read_downloaded_report(path: str | Path | None) -> list[dict]:
    """Treat Microsoft's missing report file as a valid empty result."""
    if not path:
        return []
    return _read_report(Path(path))


def fetch_microsoft_campaign_daily_spend(start_date: str, end_date: str) -> list[dict]:
    """Return daily campaign spend for the configured account, in Rome report time."""
    try:
        start = date.fromisoformat(start_date)
        end = date.fromisoformat(end_date)
    except ValueError as exc:
        raise MicrosoftAdsDeliveryError("Intervallo date Microsoft Ads non valido.") from exc
    if start > end:
        raise MicrosoftAdsDeliveryError("Intervallo date Microsoft Ads non valido.")

    config = load_microsoft_ads_config()
    authorization = _authorization_data(config)
    try:
        from bingads.v13.reporting import ReportingDownloadParameters, ReportingServiceManager

        with tempfile.TemporaryDirectory(prefix="dynamica-msads-") as directory:
            manager = ReportingServiceManager(
                authorization_data=authorization,
                poll_interval_in_milliseconds=2000,
                environment=config.environment,
                working_directory=directory,
            )
            request = _build_report_request(manager, config, start, end)
            parameters = ReportingDownloadParameters(
                report_request=request,
                result_file_directory=directory,
                result_file_name="microsoft_ads_spend.csv",
                overwrite_result_file=True,
                timeout_in_milliseconds=180000,
            )
            report_path = manager.download_file(parameters)
            return _read_downloaded_report(report_path)
    except MicrosoftAdsDeliveryError:
        raise
    except Exception as exc:
        raise MicrosoftAdsDeliveryError(
            "Scarico spend Microsoft Ads non riuscito."
        ) from exc


def fetch_microsoft_campaign_delivery(start_date: str, end_date: str) -> list[dict]:
    """Return campaign totals using only the daily spend metric."""
    daily = fetch_microsoft_campaign_daily_spend(start_date, end_date)
    totals: dict[str, dict] = {}
    for row in daily:
        campaign_id = str(row["campaign_id"])
        item = totals.setdefault(
            campaign_id,
            {
                "platform": "Microsoft Ads",
                "campaign_id": campaign_id,
                "campaign_name": row.get("campaign_name", ""),
                "start_date": start_date,
                "end_date": end_date,
                "spend": 0.0,
                "clicks": None,
                "impressions": None,
            },
        )
        item["spend"] += float(row.get("spend") or 0)
    return list(totals.values())


def fetch_microsoft_account_details() -> dict[str, str]:
    """Read account currency and time zone for a controlled configuration check."""
    config = load_microsoft_ads_config()
    authorization = _authorization_data(config)
    try:
        from bingads.service_client import ServiceClient

        service = ServiceClient(
            service="CustomerManagementService",
            version=13,
            authorization_data=authorization,
            environment=config.environment,
        )
        response = service.GetAccount(AccountId=config.account_id)
        # The SDK may return the AdvertiserAccount directly or wrap it in
        # an ``Account`` member, depending on the generated SOAP binding.
        account = getattr(response, "Account", response)
        return {
            "account_id": str(config.account_id),
            "currency_code": str(account.CurrencyCode or ""),
            "time_zone": str(account.TimeZone or ""),
        }
    except Exception as exc:
        raise MicrosoftAdsDeliveryError(
            "Verifica account Microsoft Ads non riuscita."
        ) from exc
