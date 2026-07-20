"""Maintain daily Google Ads and Meta Ads spend for dashboard filtering."""

from __future__ import annotations

import argparse
import csv
import json
from datetime import date, datetime
from pathlib import Path
from typing import Callable
from zoneinfo import ZoneInfo

from src.config import load_settings
from src.dates import current_month_until_yesterday
from src.google_ads_client import fetch_google_campaign_daily_spend
from src.meta_ads_client import fetch_meta_campaign_daily_spend


ROOT = Path(__file__).resolve().parents[1]
DAILY_COLUMNS = ["date", "source", "campaign_id", "campaign_name", "spend"]
SOURCE_NAMES = {"Google Ads": "google_ads", "Meta Ads": "meta_ads"}
EXCLUDED_META_CAMPAIGNS = {
    "dyn_veloce leadgen dip - cqd | cbo scaling (f3)",
    "recruitment assicuratori 2026",
}
EXCLUDED_META_CAMPAIGN_IDS = {"6936446163375"}
DailyFetcher = Callable[[str, str], list[dict]]


def validate_date_range(start_date: date, end_date: date) -> None:
    if start_date > end_date:
        raise ValueError("La data iniziale non può essere successiva alla data finale.")


def extract_daily_spend(
    start_date: date,
    end_date: date,
    output_path: Path = Path("data/report_daily.csv"),
    google_fetcher: DailyFetcher = fetch_google_campaign_daily_spend,
    meta_fetcher: DailyFetcher = fetch_meta_campaign_daily_spend,
) -> tuple[Path, dict]:
    """Fetch both APIs, merge history and deduplicate the queried interval."""
    validate_date_range(start_date, end_date)
    statuses: dict[str, dict[str, str | int | None]] = {}
    fetched_by_source: dict[str, list[dict]] = {}
    for platform, fetcher in (("Google Ads", google_fetcher), ("Meta Ads", meta_fetcher)):
        source = SOURCE_NAMES[platform]
        try:
            platform_rows = fetcher(start_date.isoformat(), end_date.isoformat())
            normalized = []
            for row in platform_rows:
                campaign_name = str(row.get("campaign_name") or "").strip()
                campaign_id = str(row.get("campaign_id") or "").strip()
                if source == "meta_ads" and (
                    campaign_name.casefold() in EXCLUDED_META_CAMPAIGNS
                    or campaign_id in EXCLUDED_META_CAMPAIGN_IDS
                ):
                    continue
                normalized.append(
                    {
                        "date": str(row.get("date") or ""),
                        "source": source,
                        "campaign_id": campaign_id,
                        "campaign_name": campaign_name,
                        "spend": float(row.get("spend") or 0),
                    }
                )
            fetched_by_source[source] = normalized
            statuses[platform] = {"status": "ok", "rows": len(normalized), "error": None}
        except Exception as exc:
            statuses[platform] = {"status": "error", "rows": 0, "error": str(exc)}

    if all(item["status"] == "error" for item in statuses.values()):
        raise RuntimeError("Nessuna API Ads disponibile; il file precedente non è stato modificato.")

    resolved = output_path if output_path.is_absolute() else ROOT / output_path
    resolved.parent.mkdir(parents=True, exist_ok=True)
    existing: list[dict] = []
    if resolved.exists():
        with resolved.open("r", newline="", encoding="utf-8-sig") as stream:
            for row in csv.DictReader(stream):
                source = str(row.get("source") or row.get("platform") or "").strip()
                source = SOURCE_NAMES.get(source, source)
                existing.append(
                    {
                        "date": str(row.get("date") or ""),
                        "source": source,
                        "campaign_id": str(row.get("campaign_id") or "").strip(),
                        "campaign_name": str(row.get("campaign_name") or "").strip(),
                        "spend": float(row.get("spend") or 0),
                    }
                )

    successful_sources = set(fetched_by_source)
    merged = []
    for row in existing:
        in_range = start_date.isoformat() <= row["date"] <= end_date.isoformat()
        if in_range and row["source"] in successful_sources:
            continue
        merged.append(row)
    for source_rows in fetched_by_source.values():
        merged.extend(source_rows)

    deduplicated = {
        (row["date"], row["source"], row["campaign_id"]): row
        for row in merged
        if row["date"] and row["source"] and row["campaign_id"]
    }
    final_rows = sorted(deduplicated.values(), key=lambda row: (row["date"], row["source"], row["campaign_id"]))
    temporary_path = resolved.with_suffix(resolved.suffix + ".tmp")
    with temporary_path.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=DAILY_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(final_rows)
    temporary_path.replace(resolved)

    settings = load_settings()
    status_path = resolved.with_name("report_daily_status.json")
    status_path.write_text(
        json.dumps(
            {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "updated_at": datetime.now(ZoneInfo(settings.timezone)).isoformat(timespec="seconds"),
                "sources": statuses,
            },
            ensure_ascii=False,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )
    return resolved, statuses


def _parse_args() -> argparse.Namespace:
    default_start, default_end = current_month_until_yesterday()
    parser = argparse.ArgumentParser(description="Estrae lo speso giornaliero Ads in sola lettura.")
    parser.add_argument("--start-date", type=date.fromisoformat, default=default_start)
    parser.add_argument("--end-date", type=date.fromisoformat, default=default_end)
    parser.add_argument("--output", type=Path, default=Path("data/report_daily.csv"))
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        path, statuses = extract_daily_spend(args.start_date, args.end_date, args.output)
    except (ValueError, RuntimeError) as exc:
        print(f"Errore: {exc}")
        return 1
    print(f"Storico giornaliero aggiornato: {path}")
    for platform, result in statuses.items():
        suffix = f" ({result['error']})" if result["error"] else ""
        print(f"{platform}: {result['status']}, righe={result['rows']}{suffix}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
