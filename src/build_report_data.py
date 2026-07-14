"""Build the final ``data/report_data.csv`` from manual and Ads API data."""

from __future__ import annotations

import calendar
import csv
import json
from collections.abc import Callable
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from src.ads_verification import fetch_delivery_with_status
from src.config import load_settings
from src.dates import current_month_until_yesterday
from src.google_ads_client import fetch_google_campaign_delivery
from src.google_sheets_client import fetch_manual_inputs
from src.meta_ads_client import fetch_meta_campaign_delivery
from src.utils import safe_divide


ROOT = Path(__file__).resolve().parents[1]
REPORT_COLUMNS = [
    "report_date", "start_date", "end_date", "excel_row", "funnel",
    "platform", "channel", "campaign_name", "investimento_media",
    "percentuale_investimento", "cpp_medio", "stima_pratiche", "cpl_target",
    "stima_lead", "stima_lead_giornaliere", "stima_lead_progressiva",
    "lead_effettive", "delta_lead", "stima_spending_progressiva",
    "speso_effettivo", "delta_speso", "delta_delivery_pct", "cpl_effettivo",
    "delta_cpl", "action", "google_campaign_id", "meta_campaign_id",
    "dynamics_campaign_key", "source_status",
]
DELIVERY_COLUMNS = [
    "platform", "campaign_id", "campaign_name", "start_date", "end_date",
    "spend", "clicks", "impressions",
]

ManualFetcher = Callable[[], list[dict]]
DeliveryFetcher = Callable[[str, str], list[dict]]


def _number(value: object) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _index_delivery(rows: list[dict]) -> tuple[dict[str, dict], dict[str, list[dict]]]:
    by_id: dict[str, dict] = {}
    by_name: dict[str, list[dict]] = {}
    for row in rows:
        campaign_id = str(row.get("campaign_id") or "").strip()
        campaign_name = str(row.get("campaign_name") or "").strip()
        if campaign_id:
            by_id[campaign_id] = row
        if campaign_name:
            by_name.setdefault(campaign_name.casefold(), []).append(row)
    return by_id, by_name


def _match_spend(
    manual: dict,
    api_rows: list[dict],
    id_column: str,
    platform_key: str,
    connection_status: str,
) -> tuple[float | None, str]:
    if connection_status != "ok":
        return None, f"{platform_key}:error"

    by_id, by_name = _index_delivery(api_rows)
    campaign_id = str(manual.get(id_column) or "").strip()
    if campaign_id:
        match = by_id.get(campaign_id)
        if match is None:
            return 0.0, f"{platform_key}:no_delivery"
        return float(match.get("spend") or 0), f"{platform_key}:ok"

    campaign_name = str(manual.get("campaign_name") or "").strip()
    name_matches = by_name.get(campaign_name.casefold(), [])
    if len(name_matches) == 1:
        return float(name_matches[0].get("spend") or 0), f"{platform_key}:ok_name_fallback"
    if len(name_matches) > 1:
        return None, f"{platform_key}:ambiguous_name"
    return 0.0, f"{platform_key}:no_delivery_name"


def _platforms_for_row(row: dict) -> list[tuple[str, str]]:
    platforms: list[tuple[str, str]] = []
    if str(row.get("google_campaign_id") or "").strip():
        platforms.append(("google", "google_campaign_id"))
    if str(row.get("meta_campaign_id") or "").strip():
        platforms.append(("meta", "meta_campaign_id"))
    if platforms:
        return platforms

    platform = str(row.get("platform") or "").casefold()
    if "google" in platform:
        return [("google", "google_campaign_id")]
    if "meta" in platform or "facebook" in platform or "instagram" in platform:
        return [("meta", "meta_campaign_id")]
    return []


def build_report_rows(
    manual_rows: list[dict],
    google_rows: list[dict],
    meta_rows: list[dict],
    start_date: date,
    end_date: date,
    google_status: str = "ok",
    meta_status: str = "ok",
    report_date: date | None = None,
) -> list[dict]:
    """Pure merge/calculation function, kept injectable for technical mocks."""
    report_date = report_date or date.today()
    days_in_month = calendar.monthrange(start_date.year, start_date.month)[1]
    elapsed_days = max((end_date - start_date).days + 1, 0)
    delivery = {"google": google_rows, "meta": meta_rows}
    statuses = {"google": google_status, "meta": meta_status}
    id_columns = {"google": "google_campaign_id", "meta": "meta_campaign_id"}
    output: list[dict] = []

    for manual in manual_rows:
        spend_parts: list[float] = []
        source_parts: list[str] = []
        platforms = _platforms_for_row(manual)
        for platform_key, id_column in platforms:
            spend, source = _match_spend(
                manual,
                delivery[platform_key],
                id_column or id_columns[platform_key],
                platform_key,
                statuses[platform_key],
            )
            source_parts.append(source)
            if spend is not None:
                spend_parts.append(spend)

        connection_failed = any(
            statuses[key] != "ok" for key, _ in platforms
        )
        speso_effettivo = None if connection_failed else (sum(spend_parts) if platforms else None)
        investimento = _number(manual.get("investimento_media"))
        stima_lead = _number(manual.get("stima_lead"))
        lead_effettive = _number(manual.get("lead_effettive_manual"))
        cpl_target = _number(manual.get("cpl_target"))

        stima_lead_giornaliere = safe_divide(stima_lead, days_in_month)
        stima_lead_progressiva = (
            stima_lead_giornaliere * elapsed_days
            if stima_lead_giornaliere is not None else None
        )
        stima_spending_progressiva = (
            investimento / days_in_month * elapsed_days
            if investimento is not None else None
        )
        delta_lead = (
            lead_effettive - stima_lead_progressiva
            if lead_effettive is not None and stima_lead_progressiva is not None else None
        )
        delta_speso = (
            speso_effettivo - stima_spending_progressiva
            if speso_effettivo is not None and stima_spending_progressiva is not None else None
        )
        delta_delivery_pct = safe_divide(delta_speso, stima_spending_progressiva)
        cpl_effettivo = safe_divide(speso_effettivo, lead_effettive)
        delta_cpl = (
            cpl_effettivo - cpl_target
            if cpl_effettivo is not None and cpl_target is not None else None
        )

        output.append(
            {
                "report_date": report_date.isoformat(),
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "excel_row": manual.get("excel_row"),
                "funnel": manual.get("funnel"),
                "platform": manual.get("platform"),
                "channel": manual.get("channel"),
                "campaign_name": manual.get("campaign_name"),
                "investimento_media": investimento,
                "percentuale_investimento": _number(manual.get("percentuale_investimento")),
                "cpp_medio": _number(manual.get("cpp_medio")),
                "stima_pratiche": _number(manual.get("stima_pratiche")),
                "cpl_target": cpl_target,
                "stima_lead": stima_lead,
                "stima_lead_giornaliere": stima_lead_giornaliere,
                "stima_lead_progressiva": stima_lead_progressiva,
                "lead_effettive": lead_effettive,
                "delta_lead": delta_lead,
                "stima_spending_progressiva": stima_spending_progressiva,
                "speso_effettivo": speso_effettivo,
                "delta_speso": delta_speso,
                "delta_delivery_pct": delta_delivery_pct,
                "cpl_effettivo": cpl_effettivo,
                "delta_cpl": delta_cpl,
                "action": manual.get("action"),
                "google_campaign_id": str(manual.get("google_campaign_id") or ""),
                "meta_campaign_id": str(manual.get("meta_campaign_id") or ""),
                "dynamics_campaign_key": str(manual.get("dynamics_campaign_key") or ""),
                "source_status": ";".join(source_parts) if source_parts else "manual:no_ads_source",
            }
        )
    return output


def _write_csv(path: Path, rows: list[dict], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def build_report_data(
    output_path: Path = Path("data/report_data.csv"),
    today: date | None = None,
    manual_fetcher: ManualFetcher | None = None,
    google_fetcher: DeliveryFetcher | None = None,
    meta_fetcher: DeliveryFetcher | None = None,
) -> Path:
    """Run the read-only sources and generate CSV plus safe update metadata."""
    today = today or date.today()
    start, end = current_month_until_yesterday(today)
    manual_fetcher = manual_fetcher or fetch_manual_inputs
    google_fetcher = google_fetcher or fetch_google_campaign_delivery
    meta_fetcher = meta_fetcher or fetch_meta_campaign_delivery

    manual_rows = manual_fetcher()
    google_rows, google_verification, google_status, google_error = fetch_delivery_with_status(
        "Google Ads", google_fetcher, start.isoformat(), end.isoformat()
    )
    meta_rows, meta_verification, meta_status, meta_error = fetch_delivery_with_status(
        "Meta Ads", meta_fetcher, start.isoformat(), end.isoformat()
    )
    output_path = output_path if output_path.is_absolute() else ROOT / output_path
    _write_csv(ROOT / "data/raw/google_ads_raw.csv", google_rows, DELIVERY_COLUMNS)
    _write_csv(ROOT / "data/raw/meta_ads_raw.csv", meta_rows, DELIVERY_COLUMNS)
    verification_rows = google_verification + meta_verification
    _write_csv(
        ROOT / "data/raw/ads_delivery_verification.csv",
        verification_rows,
        ["platform", "campaign_id", "campaign_name", "periodo_interrogato",
         "speso_estratto", "stato_collegamento", "errore"],
    )

    settings = load_settings()
    errors = [error for error in (google_error, meta_error) if error]
    if errors:
        raise RuntimeError(
            "Aggiornamento interrotto: i collegamenti Ads non sono tutti disponibili. "
            "I file latest precedenti sono rimasti invariati."
        )

    rows = build_report_rows(
        manual_rows, google_rows, meta_rows, start, end,
        google_status=google_status, meta_status=meta_status, report_date=today,
    )
    _write_csv(output_path, rows, REPORT_COLUMNS)
    metadata = {
        "client": settings.client_name,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "updated_at": datetime.now(ZoneInfo(settings.timezone)).isoformat(timespec="seconds"),
        "status": "ok",
    }
    metadata_path = ROOT / "data/last_update.json"
    metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return output_path


def main() -> int:
    try:
        path = build_report_data()
    except RuntimeError as exc:
        print(f"Errore: {exc}")
        return 1
    print(f"Report generato: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
