"""Download CRM Excel attachments from Outlook using Microsoft Graph."""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import tempfile
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable
from urllib.parse import quote
from zoneinfo import ZoneInfo

import msal
import pandas as pd
import requests
from dotenv import load_dotenv

from src.crm_excel_client import CRMExportError, read_crm_export_frame


ROOT = Path(__file__).resolve().parents[1]
GRAPH_ROOT = "https://graph.microsoft.com/v1.0"
STATUS_FILENAME = ".outlook_crm_status.json"


class OutlookCRMError(RuntimeError):
    """Raised when Outlook cannot provide a safe, valid CRM attachment."""


@dataclass(frozen=True)
class OutlookSettings:
    tenant_id: str
    client_id: str
    client_secret: str
    mailbox: str
    input_dir: Path
    subject: str = "DYNAMICA CRM"
    attachment_pattern: str = "*.xlsx"
    lookback_days: int = 14
    timeout_seconds: float = 30.0
    max_messages: int = 200
    retry_attempts: int = 3
    retry_delay_seconds: float = 900.0
    timezone_name: str = "Europe/Rome"


@dataclass(frozen=True)
class DownloadResult:
    path: Path | None
    message_received_at: datetime | None
    attachment_name: str | None
    downloaded: bool
    message_id: str | None = None
    content_sha256: str | None = None
    already_processed: bool = False


def _input_dir(path: str | Path | None = None) -> Path:
    configured = Path(
        path or os.getenv("CRM_EXPORT_DIR", "data/input").strip() or "data/input"
    )
    return configured if configured.is_absolute() else ROOT / configured


def read_outlook_status(input_dir: str | Path | None = None) -> dict:
    """Read the local, privacy-safe Outlook ingestion status."""
    path = _input_dir(input_dir) / STATUS_FILENAME
    if not path.exists():
        return {"status": "missing"}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"status": "invalid"}
    return payload if isinstance(payload, dict) else {"status": "invalid"}


def _write_outlook_status(
    input_dir: Path,
    status: str,
    *,
    error: str | None = None,
    result: DownloadResult | None = None,
) -> dict:
    """Atomically persist status without email bodies, lead data or secrets."""
    previous = read_outlook_status(input_dir)
    payload: dict = {
        "status": status,
        "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    last_success = previous.get("last_success")
    if isinstance(last_success, dict):
        payload["last_success"] = last_success
    if result is not None and result.path is not None:
        payload["last_success"] = {
            "message_id": result.message_id,
            "message_received_at": (
                result.message_received_at.isoformat(timespec="seconds")
                if result.message_received_at
                else None
            ),
            "attachment_name": result.attachment_name,
            "content_sha256": result.content_sha256,
            "path": result.path.name,
        }
    if error:
        payload["error"] = error
    input_dir.mkdir(parents=True, exist_ok=True)
    target = input_dir / STATUS_FILENAME
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            suffix=".json",
            prefix=".outlook-status-",
            dir=input_dir,
            delete=False,
        ) as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            temp_path = Path(stream.name)
        temp_path.replace(target)
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink()
    return payload


def load_outlook_settings() -> OutlookSettings:
    """Load app-only Graph settings from the ignored local environment file."""
    load_dotenv(ROOT / ".env", encoding="utf-8-sig")
    reuse_dynamics = (
        os.getenv("OUTLOOK_REUSE_DYNAMICS_CREDENTIALS", "false")
        .strip()
        .casefold()
        == "true"
    )
    tenant_id = os.getenv("OUTLOOK_TENANT_ID", "").strip()
    client_id = os.getenv("OUTLOOK_CLIENT_ID", "").strip()
    client_secret = os.getenv("OUTLOOK_CLIENT_SECRET", "").strip()
    if reuse_dynamics:
        tenant_id = tenant_id or os.getenv("DYNAMICS_TENANT_ID", "").strip()
        client_id = client_id or os.getenv("DYNAMICS_CLIENT_ID", "").strip()
        client_secret = client_secret or os.getenv("DYNAMICS_CLIENT_SECRET", "").strip()
    mailbox = os.getenv("OUTLOOK_MAILBOX", "dyn.leadgen@tig.it").strip()
    missing = [
        name
        for name, value in (
            ("OUTLOOK_TENANT_ID", tenant_id),
            ("OUTLOOK_CLIENT_ID", client_id),
            ("OUTLOOK_CLIENT_SECRET", client_secret),
            ("OUTLOOK_MAILBOX", mailbox),
        )
        if not value
    ]
    if missing:
        raise OutlookCRMError(
            "Configurazione Outlook incompleta: " + ", ".join(missing)
        )
    input_dir = _input_dir()
    try:
        lookback_days = int(os.getenv("OUTLOOK_LOOKBACK_DAYS", "14"))
        max_messages = int(os.getenv("OUTLOOK_MAX_MESSAGES", "200"))
        timeout_seconds = float(os.getenv("OUTLOOK_TIMEOUT_SECONDS", "30"))
        retry_attempts = int(os.getenv("OUTLOOK_RETRY_ATTEMPTS", "3"))
        retry_delay_seconds = float(
            os.getenv("OUTLOOK_RETRY_DELAY_SECONDS", "900")
        )
    except ValueError as exc:
        raise OutlookCRMError("Configurazione numerica Outlook non valida.") from exc
    if (
        lookback_days < 1
        or max_messages < 1
        or timeout_seconds <= 0
        or retry_attempts < 1
        or retry_delay_seconds < 0
    ):
        raise OutlookCRMError("Configurazione numerica Outlook fuori intervallo.")
    return OutlookSettings(
        tenant_id=tenant_id,
        client_id=client_id,
        client_secret=client_secret,
        mailbox=mailbox,
        input_dir=input_dir,
        subject=(
            os.getenv("OUTLOOK_CRM_SUBJECT", "").strip()
            or os.getenv("OUTLOOK_CRM_SUBJECT_PREFIX", "").strip()
            or "DYNAMICA CRM"
        ),
        attachment_pattern=(
            os.getenv("OUTLOOK_CRM_ATTACHMENT_PATTERN", "*.xlsx").strip()
            or "*.xlsx"
        ),
        lookback_days=lookback_days,
        timeout_seconds=timeout_seconds,
        max_messages=max_messages,
        retry_attempts=retry_attempts,
        retry_delay_seconds=retry_delay_seconds,
        timezone_name=os.getenv("TIMEZONE", "Europe/Rome").strip() or "Europe/Rome",
    )


def _access_token(settings: OutlookSettings) -> str:
    app = msal.ConfidentialClientApplication(
        settings.client_id,
        authority=f"https://login.microsoftonline.com/{settings.tenant_id}",
        client_credential=settings.client_secret,
    )
    result = app.acquire_token_for_client(
        scopes=["https://graph.microsoft.com/.default"]
    )
    token = str(result.get("access_token") or "")
    if not token:
        code = str(result.get("error") or "authentication_failed")
        raise OutlookCRMError(f"Autenticazione Microsoft Graph fallita ({code}).")
    return token


def _get(
    session: requests.Session,
    url: str,
    headers: dict[str, str],
    timeout: float,
    params: dict[str, str] | None = None,
) -> requests.Response:
    try:
        response = session.get(url, headers=headers, params=params, timeout=timeout)
    except requests.RequestException as exc:
        raise OutlookCRMError("Microsoft Graph non raggiungibile.") from exc
    if response.status_code >= 400:
        try:
            code = str((response.json().get("error") or {}).get("code") or "")
        except ValueError:
            code = ""
        suffix = f" ({code})" if code else ""
        raise OutlookCRMError(
            f"Microsoft Graph ha risposto HTTP {response.status_code}{suffix}."
        )
    return response


def _json(response: requests.Response) -> dict:
    try:
        payload = response.json()
    except ValueError as exc:
        raise OutlookCRMError("Risposta Microsoft Graph non valida.") from exc
    if not isinstance(payload, dict):
        raise OutlookCRMError("Formato della risposta Microsoft Graph non valido.")
    return payload


def _parse_datetime(value: object) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise OutlookCRMError("Data email Outlook non valida.") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _messages(
    session: requests.Session,
    settings: OutlookSettings,
    headers: dict[str, str],
) -> list[dict]:
    since = datetime.now(timezone.utc) - timedelta(days=settings.lookback_days)
    mailbox = quote(settings.mailbox, safe="")
    url = f"{GRAPH_ROOT}/users/{mailbox}/mailFolders/inbox/messages"
    params: dict[str, str] | None = {
        "$select": "id,subject,receivedDateTime,hasAttachments",
        "$filter": (
            f"receivedDateTime ge {since.isoformat(timespec='seconds').replace('+00:00', 'Z')} "
            "and hasAttachments eq true"
        ),
        "$orderby": "receivedDateTime desc",
        "$top": "50",
    }
    messages: list[dict] = []
    while url and len(messages) < settings.max_messages:
        payload = _json(
            _get(session, url, headers, settings.timeout_seconds, params=params)
        )
        values = payload.get("value")
        if not isinstance(values, list):
            raise OutlookCRMError("Graph non ha restituito una lista di email.")
        messages.extend(item for item in values if isinstance(item, dict))
        url = str(payload.get("@odata.nextLink") or "")
        params = None
    return messages[: settings.max_messages]


def _attachments(
    session: requests.Session,
    settings: OutlookSettings,
    headers: dict[str, str],
    message_id: str,
) -> list[dict]:
    mailbox = quote(settings.mailbox, safe="")
    message = quote(message_id, safe="")
    url = f"{GRAPH_ROOT}/users/{mailbox}/messages/{message}/attachments"
    params: dict[str, str] | None = {
        "$select": "id,name,contentType,size,isInline"
    }
    attachments: list[dict] = []
    while url:
        payload = _json(
            _get(session, url, headers, settings.timeout_seconds, params=params)
        )
        values = payload.get("value")
        if not isinstance(values, list):
            raise OutlookCRMError("Graph non ha restituito una lista di allegati.")
        attachments.extend(item for item in values if isinstance(item, dict))
        url = str(payload.get("@odata.nextLink") or "")
        params = None
    return attachments


def _download_attachment(
    session: requests.Session,
    settings: OutlookSettings,
    headers: dict[str, str],
    message_id: str,
    attachment_id: str,
) -> bytes:
    mailbox = quote(settings.mailbox, safe="")
    message = quote(message_id, safe="")
    attachment = quote(attachment_id, safe="")
    url = (
        f"{GRAPH_ROOT}/users/{mailbox}/messages/{message}/attachments/"
        f"{attachment}/$value"
    )
    return _get(session, url, headers, settings.timeout_seconds).content


def _validate_workbook(path: Path) -> None:
    try:
        frame = read_crm_export_frame(path)
    except CRMExportError as exc:
        raise OutlookCRMError("L'allegato Excel CRM non è valido.") from exc
    lead_ids = frame["Id Lead"].fillna("").astype(str).str.strip()
    created_at = pd.to_datetime(
        frame["Data e ora di creazione"], errors="coerce"
    )
    if lead_ids.eq("").any() or created_at.isna().any():
        raise OutlookCRMError("L'allegato Excel CRM contiene dati non validi.")


def _same_file(path: Path, content: bytes) -> bool:
    if not path.exists() or path.stat().st_size != len(content):
        return False
    return hashlib.sha256(path.read_bytes()).digest() == hashlib.sha256(content).digest()


def _save_validated(
    content: bytes,
    attachment_name: str,
    received_at: datetime,
    input_dir: Path,
) -> tuple[Path, bool]:
    safe_name = Path(attachment_name).name
    if not safe_name.casefold().endswith(".xlsx"):
        raise OutlookCRMError("L'allegato CRM non è un file .xlsx.")
    input_dir.mkdir(parents=True, exist_ok=True)
    target = input_dir / safe_name
    if _same_file(target, content):
        timestamp = received_at.timestamp()
        os.utime(target, (timestamp, timestamp))
        return target, False
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            suffix=".xlsx", prefix=".outlook-crm-", dir=input_dir, delete=False
        ) as stream:
            stream.write(content)
            temp_path = Path(stream.name)
        _validate_workbook(temp_path)
        temp_path.replace(target)
        timestamp = received_at.timestamp()
        os.utime(target, (timestamp, timestamp))
        return target, True
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink()


def download_latest_crm_attachment(
    *,
    settings: OutlookSettings | None = None,
    attachment_name: str | None = None,
    received_on: date | None = None,
    session: requests.Session | None = None,
    token_provider=_access_token,
) -> DownloadResult:
    """Download the newest matching valid workbook without changing any email."""
    settings = settings or load_outlook_settings()
    session = session or requests.Session()
    token = token_provider(settings)
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    exact_name = str(attachment_name or "").strip()
    previous = read_outlook_status(settings.input_dir)
    last_success = previous.get("last_success")
    if not isinstance(last_success, dict):
        last_success = {}
    for message in _messages(session, settings, headers):
        subject = str(message.get("subject") or "").strip()
        if (
            not exact_name
            and settings.subject
            and subject.casefold() != settings.subject.strip().casefold()
        ):
            continue
        message_id = str(message.get("id") or "")
        if not message_id:
            continue
        received_at = _parse_datetime(message.get("receivedDateTime"))
        if (
            received_on is not None
            and received_at.astimezone(ZoneInfo(settings.timezone_name)).date()
            != received_on
        ):
            continue
        for attachment in _attachments(session, settings, headers, message_id):
            name = str(attachment.get("name") or "")
            if bool(attachment.get("isInline")):
                continue
            if exact_name:
                matches = name.casefold() == exact_name.casefold()
            else:
                matches = fnmatch.fnmatch(name.casefold(), settings.attachment_pattern.casefold())
            if not matches:
                continue
            attachment_id = str(attachment.get("id") or "")
            if not attachment_id:
                continue
            existing_path = settings.input_dir / Path(name).name
            if (
                message_id == str(last_success.get("message_id") or "")
                and name == str(last_success.get("attachment_name") or "")
                and existing_path.exists()
            ):
                return DownloadResult(
                    existing_path,
                    received_at,
                    name,
                    False,
                    message_id,
                    str(last_success.get("content_sha256") or "") or None,
                    True,
                )
            content = _download_attachment(
                session, settings, headers, message_id, attachment_id
            )
            try:
                path, downloaded = _save_validated(
                    content, name, received_at, settings.input_dir
                )
            except OutlookCRMError:
                continue
            return DownloadResult(
                path,
                received_at,
                name,
                downloaded,
                message_id,
                hashlib.sha256(content).hexdigest(),
                False,
            )
    return DownloadResult(None, None, None, False)


def download_crm_with_retries(
    *,
    settings: OutlookSettings | None = None,
    attachment_name: str | None = None,
    run_date: date | None = None,
    downloader: Callable[..., DownloadResult] = download_latest_crm_attachment,
    sleeper: Callable[[float], None] = time.sleep,
) -> DownloadResult:
    """Retry a missing/new CRM email and persist a safe ingestion status."""
    settings = settings or load_outlook_settings()
    attempts = 1 if attachment_name else settings.retry_attempts
    received_on = None if attachment_name else (
        run_date or datetime.now(ZoneInfo(settings.timezone_name)).date()
    )
    last_error: OutlookCRMError | None = None
    last_result = DownloadResult(None, None, None, False)
    for attempt in range(1, attempts + 1):
        try:
            last_result = downloader(
                settings=settings,
                attachment_name=attachment_name,
                received_on=received_on,
            )
            if last_result.path is not None:
                _write_outlook_status(settings.input_dir, "ok", result=last_result)
                return last_result
        except OutlookCRMError as exc:
            last_error = exc
        if attempt < attempts:
            print(
                f"Nessun nuovo allegato CRM valido (tentativo {attempt}/{attempts}); "
                f"nuovo controllo tra {int(settings.retry_delay_seconds // 60)} minuti."
            )
            sleeper(settings.retry_delay_seconds)

    if last_error is not None:
        _write_outlook_status(
            settings.input_dir,
            "error",
            error=str(last_error),
        )
        raise last_error
    _write_outlook_status(
        settings.input_dir,
        "stale",
        error="Nessun nuovo allegato Excel CRM valido trovato.",
    )
    return last_result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attachment-name")
    args = parser.parse_args()
    load_dotenv(ROOT / ".env", encoding="utf-8-sig")
    if os.getenv("OUTLOOK_ENABLED", "false").strip().casefold() != "true" and not args.attachment_name:
        print("Download Outlook CRM disattivato.")
        return 0
    try:
        settings = load_outlook_settings()
        result = download_crm_with_retries(
            settings=settings,
            attachment_name=args.attachment_name
        )
    except OutlookCRMError as exc:
        print(f"Download Outlook CRM fallito: {exc}")
        return 1
    if result.already_processed:
        print(f"Allegato CRM già elaborato: {result.path.name}")
        return 0
    if result.path is None:
        print("Nessun nuovo allegato Excel CRM valido trovato.")
        return 0
    action = "scaricato" if result.downloaded else "già presente"
    print(f"Allegato CRM {action}: {result.path.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
