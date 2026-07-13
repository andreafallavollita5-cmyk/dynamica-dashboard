from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone

from meta_common import (
    graph_get_all,
    load_meta_settings,
    normalize_ad_account_id,
    resolve_db_path,
)


LEAD_ACTION_PRIORITY = (
    "lead",
    "onsite_web_lead",
    "offsite_conversion.fb_pixel_lead",
    "onsite_conversion.lead_grouped",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export Meta Ads campaign insights.")
    parser.add_argument("--ad-account-id", help="Meta ad account ID, with or without act_.")
    parser.add_argument("--date-preset", default="last_30d")
    parser.add_argument("--db", help="SQLite database path.")
    return parser.parse_args()


def ensure_db(db_path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS meta_campaign_performance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fetched_at TEXT NOT NULL,
                ad_account_id TEXT NOT NULL,
                date_preset TEXT NOT NULL,
                date_start TEXT,
                date_stop TEXT,
                campaign_id TEXT,
                campaign_name TEXT NOT NULL,
                channel TEXT NOT NULL,
                spend REAL NOT NULL,
                clicks INTEGER NOT NULL,
                impressions INTEGER NOT NULL,
                leads REAL NOT NULL,
                cpl REAL,
                actions_json TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_meta_campaign_performance_lookup
            ON meta_campaign_performance (
                ad_account_id,
                date_preset,
                campaign_id,
                fetched_at
            )
            """
        )


def action_value(actions: list[dict], priority: tuple[str, ...]) -> float:
    values = {
        str(action.get("action_type", "")).lower(): float(action.get("value") or 0)
        for action in actions or []
    }
    for action_type in priority:
        if action_type in values:
            return values[action_type]
    return 0.0


def save_rows(db_path, rows: list[tuple]) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.executemany(
            """
            INSERT INTO meta_campaign_performance (
                fetched_at,
                ad_account_id,
                date_preset,
                date_start,
                date_stop,
                campaign_id,
                campaign_name,
                channel,
                spend,
                clicks,
                impressions,
                leads,
                cpl,
                actions_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )


def main() -> None:
    args = parse_args()
    settings = load_meta_settings()
    access_token = settings["access_token"]
    ad_account_id = normalize_ad_account_id(args.ad_account_id or settings["ad_account_id"])
    db_path = resolve_db_path(args.db or settings["db_path"])

    if not access_token:
        raise RuntimeError("Missing META_ACCESS_TOKEN in .env")
    if not ad_account_id:
        raise RuntimeError("Missing META_AD_ACCOUNT_ID in .env or --ad-account-id")

    ensure_db(db_path)
    path = f"{settings['api_version']}/act_{ad_account_id}/insights"
    fields = [
        "campaign_id",
        "campaign_name",
        "spend",
        "clicks",
        "impressions",
        "actions",
        "date_start",
        "date_stop",
    ]
    rows = graph_get_all(
        path,
        {
            "access_token": access_token,
            "level": "campaign",
            "date_preset": args.date_preset,
            "fields": ",".join(fields),
            "limit": 500,
        },
    )

    fetched_at = datetime.now(timezone.utc).isoformat()
    output_rows = []
    for row in rows:
        spend = float(row.get("spend") or 0)
        leads = action_value(row.get("actions", []), LEAD_ACTION_PRIORITY)
        cpl = spend / leads if leads else None
        output_rows.append(
            (
                fetched_at,
                ad_account_id,
                args.date_preset,
                row.get("date_start"),
                row.get("date_stop"),
                row.get("campaign_id"),
                row.get("campaign_name") or "(senza nome campagna)",
                "META",
                spend,
                int(row.get("clicks") or 0),
                int(row.get("impressions") or 0),
                leads,
                cpl,
                json.dumps(row.get("actions", []), ensure_ascii=True),
            )
        )

    save_rows(db_path, output_rows)
    print(f"Salvate {len(output_rows)} righe Meta in {db_path}")
    if not output_rows:
        print("Nessuna campagna trovata per il periodo richiesto.")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as exc:
        print(f"Errore: {exc}", file=sys.stderr)
        raise SystemExit(1)
