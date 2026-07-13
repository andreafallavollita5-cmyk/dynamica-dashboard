from __future__ import annotations

import argparse
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from google_ads_common import google_ads_client, load_settings, normalize_customer_id


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export Google Ads campaign metrics.")
    parser.add_argument("--customer-id", help="Google Ads customer ID to query.")
    parser.add_argument("--login-customer-id", help="Manager/MCC customer ID.")
    parser.add_argument(
        "--during",
        default="LAST_30_DAYS",
        help="GAQL date range, for example LAST_7_DAYS, LAST_30_DAYS, THIS_MONTH.",
    )
    parser.add_argument("--db", help="SQLite database path.")
    return parser.parse_args()


def ensure_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS campaign_performance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fetched_at TEXT NOT NULL,
                customer_id TEXT NOT NULL,
                date_filter TEXT NOT NULL,
                campaign_id INTEGER NOT NULL,
                campaign_name TEXT NOT NULL,
                advertising_channel_type TEXT NOT NULL,
                cost_micros INTEGER NOT NULL,
                cost REAL NOT NULL,
                clicks INTEGER NOT NULL,
                impressions INTEGER NOT NULL,
                conversions REAL NOT NULL,
                cpl REAL
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_campaign_performance_lookup
            ON campaign_performance (customer_id, date_filter, campaign_id, fetched_at)
            """
        )


def enum_name(value: object) -> str:
    return getattr(value, "name", str(value))


def save_rows(db_path: Path, rows: list[tuple]) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.executemany(
            """
            INSERT INTO campaign_performance (
                fetched_at,
                customer_id,
                date_filter,
                campaign_id,
                campaign_name,
                advertising_channel_type,
                cost_micros,
                cost,
                clicks,
                impressions,
                conversions,
                cpl
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )


def main() -> None:
    args = parse_args()
    settings = load_settings()
    customer_id = normalize_customer_id(args.customer_id) or settings["customer_id"]
    login_customer_id = (
        normalize_customer_id(args.login_customer_id) or settings["login_customer_id"]
    )
    db_path = Path(args.db or settings["db_path"])
    if not db_path.is_absolute():
        db_path = Path(__file__).resolve().parents[1] / db_path

    if not customer_id:
        raise RuntimeError(
            "Missing customer ID. Set GOOGLE_ADS_CUSTOMER_ID or pass --customer-id."
        )

    ensure_db(db_path)
    client = google_ads_client(login_customer_id=login_customer_id)
    service = client.get_service("GoogleAdsService")
    query = f"""
        SELECT
          campaign.id,
          campaign.name,
          campaign.advertising_channel_type,
          metrics.cost_micros,
          metrics.clicks,
          metrics.impressions,
          metrics.conversions
        FROM campaign
        WHERE segments.date DURING {args.during}
        ORDER BY metrics.cost_micros DESC
    """

    fetched_at = datetime.now(timezone.utc).isoformat()
    output_rows = []
    response = service.search_stream(customer_id=customer_id, query=query)

    for batch in response:
        for row in batch.results:
            cost_micros = int(row.metrics.cost_micros or 0)
            cost = cost_micros / 1_000_000
            conversions = float(row.metrics.conversions or 0)
            cpl = cost / conversions if conversions else None
            output_rows.append(
                (
                    fetched_at,
                    customer_id,
                    args.during,
                    int(row.campaign.id),
                    row.campaign.name,
                    enum_name(row.campaign.advertising_channel_type),
                    cost_micros,
                    cost,
                    int(row.metrics.clicks or 0),
                    int(row.metrics.impressions or 0),
                    conversions,
                    cpl,
                )
            )

    save_rows(db_path, output_rows)
    print(f"Salvate {len(output_rows)} righe in {db_path}")
    if not output_rows:
        print(
            "Nessuna campagna trovata. Se questo e un manager account, passa un "
            "customer_id cliente con --customer-id."
        )


if __name__ == "__main__":
    main()
