"""Publish only the dashboard latest artifacts to the private repository."""

from __future__ import annotations

import os
import subprocess
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
LATEST_FILES = (
    "data/report_data.csv",
    "data/report_daily_metrics.csv",
    "data/last_update.json",
    "exports/report_dynamica_updated.xlsx",
)
HISTORY_ROOT = Path("data/history")
HISTORY_FILES = (
    "report_data.csv",
    "report_daily_metrics.csv",
    "last_update.json",
)


def _git(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=ROOT, text=True, capture_output=True, check=check
    )


def _accessible_history_files(history_root: Path) -> list[Path]:
    """Return publishable monthly files, skipping unreadable legacy folders."""
    try:
        candidates = list(history_root.iterdir())
    except OSError:
        return []

    published: list[Path] = []
    for folder in sorted(candidates, key=lambda path: path.name):
        try:
            if not folder.is_dir():
                continue
            datetime.strptime(folder.name, "%Y-%m")
        except (OSError, ValueError):
            continue
        for name in HISTORY_FILES:
            path = folder / name
            try:
                if path.is_file():
                    published.append(path)
            except OSError:
                # A protected historical snapshot must not block today's latest.
                continue
    return published


def publish_latest_files(commit_message: str | None = None) -> bool:
    """Commit and push latest files plus frozen monthly dashboard history.

    Returns False when publishing is disabled or the latest files are unchanged.
    """
    load_dotenv(ROOT / ".env", encoding="utf-8-sig")
    if os.getenv("GITHUB_PUBLISH_ENABLED", "false").strip().casefold() != "true":
        return False
    missing = [path for path in LATEST_FILES if not (ROOT / path).exists()]
    if missing:
        raise FileNotFoundError("File latest mancanti: " + ", ".join(missing))

    published_paths = list(LATEST_FILES)
    history_root = ROOT / HISTORY_ROOT
    if history_root.exists():
        published_paths.extend(
            path.relative_to(ROOT).as_posix()
            for path in _accessible_history_files(history_root)
        )

    _git("add", "--", *published_paths)
    changed = _git(
        "diff", "--cached", "--quiet", "--", *published_paths, check=False
    )
    if changed.returncode == 0:
        return False
    if changed.returncode != 1:
        raise RuntimeError(changed.stderr.strip() or "Verifica Git fallita.")

    message = commit_message or (
        os.getenv("GITHUB_COMMIT_MESSAGE_PREFIX", "Aggiornamento Dynamica")
        + " "
        + datetime.now().strftime("%Y-%m-%d")
    )
    _git("commit", "-m", message, "--", *published_paths)
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
