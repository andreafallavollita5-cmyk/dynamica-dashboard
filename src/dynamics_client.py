"""Read effective leads from a Dynamics 365 Dataverse system view."""

from __future__ import annotations

import os
import re
import unicodedata
import xml.etree.ElementTree as ET
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import msal
import requests
from dotenv import load_dotenv


DEFAULT_ENVIRONMENT_URL = "https://dynamicaretail.crm4.dynamics.com"
DEFAULT_LEAD_VIEW_ID = "13950fd2-5fae-ef11-b8e9-000d3a2aa135"
DEFAULT_LEAD_TABLE = "leads"
FORMATTED_VALUE = "@OData.Community.Display.V1.FormattedValue"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class DynamicsError(RuntimeError):
    """Raised when Dataverse cannot provide a complete, trustworthy dataset."""


@dataclass(frozen=True)
class DynamicsSettings:
    tenant_id: str
    client_id: str
    client_secret: str
    environment_url: str
    lead_table: str
    lead_view_id: str
    timezone_name: str
    campaign_field: str = ""
    utm_campaign_field: str = ""
    timeout_seconds: float = 30.0


def load_dynamics_settings() -> DynamicsSettings:
    """Load Dataverse settings without exposing credentials in errors."""
    load_dotenv(os.path.join(ROOT, ".env"), encoding="utf-8-sig")
    values = {
        "DYNAMICS_TENANT_ID": os.getenv("DYNAMICS_TENANT_ID", "").strip(),
        "DYNAMICS_CLIENT_ID": os.getenv("DYNAMICS_CLIENT_ID", "").strip(),
        "DYNAMICS_CLIENT_SECRET": os.getenv("DYNAMICS_CLIENT_SECRET", "").strip(),
    }
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise DynamicsError(
            "Configurazione Dynamics incompleta: " + ", ".join(missing)
        )
    try:
        timeout = float(os.getenv("DYNAMICS_TIMEOUT_SECONDS", "30").strip() or "30")
    except ValueError as exc:
        raise DynamicsError("DYNAMICS_TIMEOUT_SECONDS non valido.") from exc
    if timeout <= 0:
        raise DynamicsError("DYNAMICS_TIMEOUT_SECONDS deve essere positivo.")
    return DynamicsSettings(
        tenant_id=values["DYNAMICS_TENANT_ID"],
        client_id=values["DYNAMICS_CLIENT_ID"],
        client_secret=values["DYNAMICS_CLIENT_SECRET"],
        environment_url=(
            os.getenv("DYNAMICS_ENVIRONMENT_URL", DEFAULT_ENVIRONMENT_URL).strip()
            or DEFAULT_ENVIRONMENT_URL
        ).rstrip("/"),
        lead_table=(
            os.getenv("DYNAMICS_LEAD_TABLE", DEFAULT_LEAD_TABLE).strip()
            or DEFAULT_LEAD_TABLE
        ),
        lead_view_id=(
            os.getenv("DYNAMICS_LEAD_VIEW_ID", DEFAULT_LEAD_VIEW_ID).strip()
            or DEFAULT_LEAD_VIEW_ID
        ),
        timezone_name=os.getenv("TIMEZONE", "Europe/Rome").strip() or "Europe/Rome",
        campaign_field=os.getenv("DYNAMICS_CAMPAIGN_FIELD", "").strip(),
        utm_campaign_field=os.getenv("DYNAMICS_UTM_CAMPAIGN_FIELD", "").strip(),
        timeout_seconds=timeout,
    )


def _access_token(settings: DynamicsSettings) -> str:
    app = msal.ConfidentialClientApplication(
        settings.client_id,
        authority=f"https://login.microsoftonline.com/{settings.tenant_id}",
        client_credential=settings.client_secret,
    )
    result = app.acquire_token_for_client(
        scopes=[f"{settings.environment_url}/.default"]
    )
    token = str(result.get("access_token") or "")
    if not token:
        error_code = str(result.get("error") or "authentication_failed")
        raise DynamicsError(f"Autenticazione Dynamics fallita ({error_code}).")
    return token


def _get_json(
    session: requests.Session,
    url: str,
    headers: dict[str, str],
    timeout: float,
    params: dict[str, str] | None = None,
) -> dict:
    try:
        response = session.get(url, headers=headers, params=params, timeout=timeout)
    except requests.RequestException as exc:
        raise DynamicsError("Dynamics non raggiungibile.") from exc
    if response.status_code >= 400:
        raise DynamicsError(f"Dynamics ha risposto HTTP {response.status_code}.")
    try:
        payload = response.json()
    except ValueError as exc:
        raise DynamicsError("Risposta Dynamics non valida.") from exc
    if not isinstance(payload, dict):
        raise DynamicsError("Formato della risposta Dynamics non valido.")
    return payload


def _normalize_label(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = text.encode("ascii", "ignore").decode("ascii").casefold()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _metadata_labels(attribute: dict) -> set[str]:
    display = attribute.get("DisplayName") or {}
    labels = display.get("LocalizedLabels") or []
    values = {
        _normalize_label(item.get("Label"))
        for item in labels
        if isinstance(item, dict)
    }
    user_label = display.get("UserLocalizedLabel") or {}
    if isinstance(user_label, dict):
        values.add(_normalize_label(user_label.get("Label")))
    return {value for value in values if value}


def _view_fetchxml(
    session: requests.Session,
    api_url: str,
    settings: DynamicsSettings,
    headers: dict[str, str],
) -> str:
    payload = _get_json(
        session,
        f"{api_url}/savedqueries({settings.lead_view_id})",
        headers,
        settings.timeout_seconds,
        params={"$select": "fetchxml,name,returnedtypecode"},
    )
    fetchxml = str(payload.get("fetchxml") or "").strip()
    if not fetchxml:
        raise DynamicsError("La vista Dynamics non contiene FetchXML.")
    if str(payload.get("returnedtypecode") or "lead").casefold() != "lead":
        raise DynamicsError("La vista Dynamics configurata non restituisce lead.")
    return fetchxml


def _root_entity(fetchxml: str) -> tuple[ET.Element, ET.Element]:
    try:
        root = ET.fromstring(fetchxml)
    except ET.ParseError as exc:
        raise DynamicsError("FetchXML della vista Dynamics non valido.") from exc
    entity = root.find("entity")
    if entity is None or str(entity.get("name") or "").casefold() != "lead":
        raise DynamicsError("La vista Dynamics non interroga la tabella lead.")
    return root, entity


def _resolve_view_fields(
    session: requests.Session,
    api_url: str,
    settings: DynamicsSettings,
    headers: dict[str, str],
    fetchxml: str,
) -> tuple[str, str]:
    if settings.campaign_field and settings.utm_campaign_field:
        return settings.campaign_field, settings.utm_campaign_field

    _root, entity = _root_entity(fetchxml)
    view_fields = {
        str(item.get("name") or "")
        for item in entity.findall("attribute")
        if item.get("name")
    }
    payload = _get_json(
        session,
        f"{api_url}/EntityDefinitions(LogicalName='lead')/Attributes",
        headers,
        settings.timeout_seconds,
        params={"$select": "LogicalName,DisplayName"},
    )
    attributes = [
        item
        for item in payload.get("value", [])
        if isinstance(item, dict)
        and str(item.get("LogicalName") or "") in view_fields
    ]

    def find_field(configured: str, wanted: tuple[str, ...], setting_name: str) -> str:
        if configured:
            return configured
        exact: list[str] = []
        partial: list[str] = []
        for attribute in attributes:
            logical = str(attribute.get("LogicalName") or "")
            labels = _metadata_labels(attribute)
            if any(label in wanted for label in labels):
                exact.append(logical)
            elif any(term in label for label in labels for term in wanted):
                partial.append(logical)
        candidates = list(dict.fromkeys(exact or partial))
        if len(candidates) != 1:
            raise DynamicsError(
                f"Campo Dynamics non identificabile in modo univoco; configurare {setting_name}."
            )
        return candidates[0]

    campaign = find_field(
        settings.campaign_field,
        ("campagna", "campaign", "campagna di origine", "originating campaign"),
        "DYNAMICS_CAMPAIGN_FIELD",
    )
    utm = find_field(
        settings.utm_campaign_field,
        ("utm campaign", "utm campagna", "campagna utm"),
        "DYNAMICS_UTM_CAMPAIGN_FIELD",
    )
    return campaign, utm


def _minimal_fetchxml(
    fetchxml: str, campaign_field: str, utm_campaign_field: str
) -> str:
    """Keep the view filters but remove every projected personal-data column."""
    root, entity = _root_entity(fetchxml)
    for current_entity in root.iter("entity"):
        for attribute in list(current_entity.findall("attribute")):
            current_entity.remove(attribute)
        current_entity.attrib.pop("all-attributes", None)
    for link in root.iter("link-entity"):
        for attribute in list(link.findall("attribute")):
            link.remove(attribute)
    for name in dict.fromkeys(
        ("leadid", "createdon", campaign_field, utm_campaign_field)
    ):
        ET.SubElement(entity, "attribute", {"name": name})
    root.set("mapping", "logical")
    root.set("distinct", "false")
    return ET.tostring(root, encoding="unicode")


def _field_value(row: dict, logical_name: str) -> str:
    direct_keys = (logical_name, f"_{logical_name}_value")
    for key in direct_keys:
        formatted = row.get(f"{key}{FORMATTED_VALUE}")
        if formatted not in (None, ""):
            return str(formatted).strip()
    for key in direct_keys:
        value = row.get(key)
        if value not in (None, ""):
            return str(value).strip()
    return ""


def _created_at(value: object, timezone_name: str) -> datetime:
    text = str(value or "").strip()
    if not text:
        raise DynamicsError("Una lead Dynamics non contiene createdon.")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise DynamicsError("Dynamics contiene una data createdon non valida.") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    try:
        return parsed.astimezone(ZoneInfo(timezone_name))
    except Exception as exc:
        raise DynamicsError("Timezone Dynamics non valida.") from exc


def fetch_effective_leads(
    start_date: str | date,
    end_date: str | date,
    *,
    settings: DynamicsSettings | None = None,
    session: requests.Session | None = None,
    token_provider: Callable[[DynamicsSettings], str] = _access_token,
    field_names: tuple[str, str] | None = None,
) -> list[dict]:
    """Return unique, normalized leads from the configured read-only system view."""
    start = date.fromisoformat(start_date) if isinstance(start_date, str) else start_date
    end = date.fromisoformat(end_date) if isinstance(end_date, str) else end_date
    if start > end:
        raise DynamicsError("Periodo Dynamics non valido.")
    settings = settings or load_dynamics_settings()
    session = session or requests.Session()
    token = token_provider(settings)
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "OData-MaxVersion": "4.0",
        "OData-Version": "4.0",
        "Prefer": 'odata.maxpagesize=5000,odata.include-annotations="OData.Community.Display.V1.FormattedValue"',
    }
    api_url = f"{settings.environment_url}/api/data/v9.2"
    fetchxml = _view_fetchxml(session, api_url, settings, headers)
    campaign_field, utm_field = field_names or _resolve_view_fields(
        session, api_url, settings, headers, fetchxml
    )
    minimal_query = _minimal_fetchxml(fetchxml, campaign_field, utm_field)

    url = f"{api_url}/{settings.lead_table}"
    params: dict[str, str] | None = {"fetchXml": minimal_query}
    records: list[dict] = []
    while url:
        payload = _get_json(
            session, url, headers, settings.timeout_seconds, params=params
        )
        values = payload.get("value")
        if not isinstance(values, list):
            raise DynamicsError("Dynamics non ha restituito una lista di lead.")
        records.extend(item for item in values if isinstance(item, dict))
        url = str(payload.get("@odata.nextLink") or "")
        params = None

    unique: dict[str, dict] = {}
    for row in records:
        lead_id = _field_value(row, "leadid")
        if not lead_id:
            raise DynamicsError("Una lead Dynamics non contiene leadid.")
        created = _created_at(_field_value(row, "createdon"), settings.timezone_name)
        if not (start <= created.date() <= end):
            continue
        normalized = {
            "lead_id": lead_id,
            "campaign_crm": _field_value(row, campaign_field),
            "utm_campaign": _field_value(row, utm_field),
            "created_at": created,
        }
        previous = unique.get(lead_id)
        if previous is None or created < previous["created_at"]:
            unique[lead_id] = normalized
    return sorted(unique.values(), key=lambda item: (item["created_at"], item["lead_id"]))
