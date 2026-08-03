"""Freeze completed monthly dashboard datasets for historical consultation."""

from __future__ import annotations

import argparse
import calendar
import json
import os
import shutil
import tempfile
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HISTORY_ROOT = ROOT / "data" / "history"
REQUIRED_FILES = (
    "report_data.csv",
    "report_daily_metrics.csv",
    "last_update.json",
)


class MonthlyHistoryError(RuntimeError):
    """Raised when a candidate snapshot is incomplete or inconsistent."""


def _metadata(source_dir: Path) -> dict:
    path = source_dir / "last_update.json"
    if not path.exists():
        raise MonthlyHistoryError(f"Metadati mancanti in {source_dir}.")
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MonthlyHistoryError(f"Metadati non validi in {source_dir}.") from exc


def completed_month_key(source_dir: Path) -> str | None:
    """Return YYYY-MM only when the source covers one complete calendar month."""
    try:
        metadata = _metadata(source_dir)
        start = date.fromisoformat(str(metadata.get("start_date") or ""))
        end = date.fromisoformat(str(metadata.get("end_date") or ""))
    except (MonthlyHistoryError, ValueError):
        return None
    month_end = calendar.monthrange(start.year, start.month)[1]
    if (
        start.day != 1
        or (start.year, start.month) != (end.year, end.month)
        or end.day != month_end
    ):
        return None
    if any(not (source_dir / name).exists() for name in REQUIRED_FILES):
        return None
    return start.strftime("%Y-%m")


def freeze_completed_month(
    source_dir: Path,
    history_root: Path = HISTORY_ROOT,
) -> Path | None:
    """Copy a complete month once; an existing frozen month is never overwritten."""
    source_dir = source_dir.resolve()
    month_key = completed_month_key(source_dir)
    if month_key is None:
        return None
    history_root.mkdir(parents=True, exist_ok=True)
    destination = history_root / month_key
    if destination.exists():
        missing = [name for name in REQUIRED_FILES if not (destination / name).exists()]
        if missing:
            raise MonthlyHistoryError(
                f"Snapshot {month_key} già presente ma incompleto: {', '.join(missing)}."
            )
        return destination

    temporary = Path(
        tempfile.mkdtemp(prefix=f".{month_key}-", dir=str(history_root))
    )
    try:
        for name in REQUIRED_FILES:
            shutil.copy2(source_dir / name, temporary / name)
        os.replace(temporary, destination)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return destination


def freeze_latest(root: Path = ROOT, history_root: Path = HISTORY_ROOT) -> Path | None:
    """Freeze the current latest dataset when it represents a completed month."""
    staging = root / "data"
    sources = {
        "report_data.csv": staging / "report_data.csv",
        "report_daily_metrics.csv": staging / "report_daily_metrics.csv",
        "last_update.json": staging / "last_update.json",
    }
    if any(not path.exists() for path in sources.values()):
        return None
    with tempfile.TemporaryDirectory(prefix="dynamica_latest_month_") as directory:
        candidate = Path(directory)
        for name, source in sources.items():
            shutil.copy2(source, candidate / name)
        return freeze_completed_month(candidate, history_root)


def backfill_from_archive(
    archive_root: Path,
    history_root: Path = HISTORY_ROOT,
) -> list[Path]:
    """Recover only complete monthly snapshots available in the local archive."""
    if not archive_root.exists():
        return []
    recovered: list[Path] = []
    for candidate in sorted(path for path in archive_root.iterdir() if path.is_dir()):
        destination = freeze_completed_month(candidate, history_root)
        if destination is not None and destination not in recovered:
            recovered.append(destination)
    return recovered


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backfill", action="store_true")
    parser.add_argument("--archive-root", type=Path, default=Path("archive"))
    args = parser.parse_args()
    archive_root = (
        args.archive_root
        if args.archive_root.is_absolute()
        else ROOT / args.archive_root
    )
    try:
        destinations: list[Path] = []
        latest = freeze_latest()
        if latest is not None:
            destinations.append(latest)
        if args.backfill:
            destinations.extend(backfill_from_archive(archive_root))
    except Exception as exc:
        print(f"Errore storico mensile: {exc}")
        return 1
    unique = sorted({path.name for path in destinations})
    if unique:
        print("Storico mensile disponibile: " + ", ".join(unique))
    else:
        print("Nessun mese completo da congelare.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
