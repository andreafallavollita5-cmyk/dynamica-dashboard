from __future__ import annotations

import argparse
import sqlite3

from meta_common import load_meta_settings, resolve_db_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Preview saved Meta Ads exports.")
    parser.add_argument("--db", help="SQLite database path.")
    parser.add_argument("--limit", type=int, default=20)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    settings = load_meta_settings()
    db_path = resolve_db_path(args.db or settings["db_path"])

    if not db_path.exists():
        raise RuntimeError(f"Database not found: {db_path}")

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        latest = conn.execute(
            "SELECT MAX(fetched_at) AS fetched_at FROM meta_campaign_performance"
        ).fetchone()["fetched_at"]
        if not latest:
            print("Database Meta vuoto.")
            return

        rows = conn.execute(
            """
            SELECT
                campaign_name,
                channel,
                spend,
                clicks,
                impressions,
                leads,
                cpl
            FROM meta_campaign_performance
            WHERE fetched_at = ?
            ORDER BY spend DESC
            LIMIT ?
            """,
            (latest, args.limit),
        ).fetchall()

    print(f"Ultimo export Meta: {latest}")
    for row in rows:
        cpl = "-" if row["cpl"] is None else f"{row['cpl']:.2f}"
        print(
            f"{row['campaign_name']} | {row['channel']} | "
            f"speso {row['spend']:.2f} | click {row['clicks']} | "
            f"impr {row['impressions']} | lead {row['leads']:.2f} | CPL {cpl}"
        )


if __name__ == "__main__":
    main()
