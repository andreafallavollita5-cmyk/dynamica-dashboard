"""Create the local dated snapshot of the dashboard's latest files."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LATEST_FILES = (
    Path("data/report_data.csv"),
    Path("data/report_daily_metrics.csv"),
    Path("exports/report_dynamica_updated.xlsx"),
    Path("data/last_update.json"),
)


def archive_latest_outputs(archive_root: Path = Path("archive")) -> Path:
    """Copy latest CSV, Excel, and metadata into a dated local archive folder."""
    metadata_path = ROOT / "data/last_update.json"
    if not metadata_path.exists():
        raise FileNotFoundError("Metadati latest non disponibili.")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    end_date = str(metadata.get("end_date") or "").strip()
    if not end_date:
        raise ValueError("Data finale mancante nei metadati.")

    root = archive_root if archive_root.is_absolute() else ROOT / archive_root
    destination = root / end_date
    destination.mkdir(parents=True, exist_ok=True)
    for relative in LATEST_FILES:
        source = ROOT / relative
        if not source.exists():
            raise FileNotFoundError(f"File latest mancante: {relative.as_posix()}")
        shutil.copy2(source, destination / source.name)
    return destination


def main() -> int:
    try:
        destination = archive_latest_outputs()
    except Exception as exc:
        print(f"Errore archivio locale: {exc}")
        return 1
    print(f"Archivio locale creato: {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
