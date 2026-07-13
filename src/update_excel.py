"""Excel export updater placeholder."""

from __future__ import annotations

from pathlib import Path


def update_excel_export(
    report_path: Path = Path("data/report_data.csv"),
    output_path: Path = Path("exports/report_dynamica_updated.xlsx"),
) -> Path:
    """Update the export workbook from report data.

    Not implemented yet: must preserve manual fields and existing formulas.
    """
    pass
