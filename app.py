"""Minimal Streamlit entry point for the Dynamica Retail dashboard.

This file intentionally avoids a full dashboard implementation for now.
It only proves that the app can load the latest CSV/JSON files that will
later be produced by the daily update flow.
"""

from __future__ import annotations

import json
from pathlib import Path


DATA_PATH = Path("data/report_data.csv")
LAST_UPDATE_PATH = Path("data/last_update.json")


def load_last_update() -> dict:
    """Load latest update metadata without exposing technical details."""
    if not LAST_UPDATE_PATH.exists():
        return {"status": "missing", "error": "last_update.json non trovato"}

    with LAST_UPDATE_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def main() -> None:
    """Render a tiny placeholder view or print a CLI summary."""
    try:
        import pandas as pd
        import streamlit as st
    except ImportError:
        metadata = load_last_update()
        print(f"Dynamica Retail dashboard skeleton - status: {metadata.get('status')}")
        return

    st.set_page_config(page_title="Dynamica Retail", layout="wide")
    st.title("Dynamica Retail")
    st.caption("Dashboard skeleton - dati mock locali")

    metadata = load_last_update()
    st.json(metadata)

    if DATA_PATH.exists():
        df = pd.read_csv(DATA_PATH)
        st.dataframe(df, use_container_width=True)
    else:
        st.warning("report_data.csv non trovato")


if __name__ == "__main__":
    main()
