from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

from google_ads_common import load_settings


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Preview saved Google Ads exports.")
    parser.add_argument("--db", help="SQLite database path.")
    parser.add_argument("--limit", type=int, default=20)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    settings = load_settings()
    db_path = Path(args.db or settings["db_path"])
    if not db_path.is_absolute():
        db_path = Path(__file__).resolve().parents[1] / db_path

    if not db_path.exists():
        raise RuntimeError(f"Database not found: {db_path}")

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        latest = conn.execute(
            "SELECT MAX(fetched_at) AS fetched_at FROM campaign_performance"
        ).fetchone()["fetched_at"]
        if not latest:
            print("Database vuoto.")
            return

        rows = conn.execute(
            """
            SELECT
                campaign_name,
                advertising_channel_type,
                cost,
                clicks,
                impressions,
                conversions,
                cpl
            FROM campaign_performance
            WHERE fetched_at = ?
            ORDER BY cost DESC
            LIMIT ?
            """,
            (latest, args.limit),
        ).fetchall()

    print(f"Ultimo export: {latest}")
    for row in rows:
        cpl = "-" if row["cpl"] is None else f"{row['cpl']:.2f}"
        print(
            f"{row['campaign_name']} | {row['advertising_channel_type']} | "
            f"speso {row['cost']:.2f} | click {row['clicks']} | "
            f"impr {row['impressions']} | conv {row['conversions']:.2f} | CPL {cpl}"
        )


if __name__ == "__main__":
    main()
