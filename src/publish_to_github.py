"""Publish only the dashboard latest artifacts to the private repository."""

from __future__ import annotations

import os
import subprocess
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LATEST_FILES = (
    "data/report_data.csv",
    "data/report_daily_metrics.csv",
    "data/last_update.json",
    "exports/report_dynamica_updated.xlsx",
)


def _git(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=ROOT, text=True, capture_output=True, check=check
    )


def publish_latest_files(commit_message: str | None = None) -> bool:
    """Commit and push only latest dashboard files when explicitly enabled.

    Returns False when publishing is disabled or the latest files are unchanged.
    """
    if os.getenv("GITHUB_PUBLISH_ENABLED", "false").strip().casefold() != "true":
        return False
    missing = [path for path in LATEST_FILES if not (ROOT / path).exists()]
    if missing:
        raise FileNotFoundError("File latest mancanti: " + ", ".join(missing))

    _git("add", "--", *LATEST_FILES)
    changed = _git("diff", "--cached", "--quiet", "--", *LATEST_FILES, check=False)
    if changed.returncode == 0:
        return False
    if changed.returncode != 1:
        raise RuntimeError(changed.stderr.strip() or "Verifica Git fallita.")

    message = commit_message or (
        os.getenv("GITHUB_COMMIT_MESSAGE_PREFIX", "Aggiornamento Dynamica")
        + " "
        + datetime.now().strftime("%Y-%m-%d")
    )
    _git("commit", "-m", message, "--", *LATEST_FILES)
    branch = os.getenv("GITHUB_BRANCH", "main").strip() or "main"
    _git("push", "origin", branch)
    return True


def main() -> int:
    try:
        published = publish_latest_files()
    except Exception as exc:
        print(f"Errore pubblicazione GitHub: {exc}")
        return 1
    print("Latest pubblicati su GitHub." if published else "Nessuna pubblicazione richiesta.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
