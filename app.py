"""Streamlit dashboard for Dynamica Retail using local latest mock data."""

from __future__ import annotations

import json
import html
import math
import os
from datetime import date, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Iterable


DATA_PATH = Path("data/report_data.csv")
REPORT_DAILY_PATH = Path("data/report_daily_metrics.csv")
REPORT_DAILY_STATUS_PATH = Path("data/report_daily_status.json")
LAST_UPDATE_PATH = Path("data/last_update.json")

DASHBOARD_TABLE_COLUMNS = {
    "funnel": "Funnel",
    "channel": "Canale",
    "campaign_name": "Campagna",
    "stima_lead_progressiva": "Stima Lead",
    "lead_effettive": "Lead Effettive",
    "delta_lead": "Delta Lead",
    "stima_spending_progressiva": "Stima Spending",
    "speso_effettivo": "Speso Effettivo",
    "delta_speso": "Delta Speso",
    "cpl_target": "CPL Target",
    "cpl_effettivo": "CPL Effettivo",
    "delta_cpl": "Delta CPL",
    "action": "Action",
}

DASHBOARD_SUMMARY_FIELDS = (
    "stima_lead_progressiva",
    "lead_effettive",
    "delta_lead",
    "stima_spending_progressiva",
    "speso_effettivo",
    "delta_speso",
    "cpl_target",
    "cpl_effettivo",
    "delta_cpl",
)
EXCLUDED_CAMPAIGN_NAMES = {
    "dyn_veloce leadgen dip - cqd | cbo scaling (f3)",
    "recruitment assicuratori 2026",
}
EXCLUDED_CAMPAIGN_IDS = {"6936446163375"}

SVG_ICONS = {
    "logo": '<svg viewBox="0 0 48 48" aria-hidden="true"><path fill="#00a5b4" d="M24 2 45 13 24 25 3 13Z"/><path fill="#008faa" d="M3 13 24 25v21L3 35Z"/><path fill="#4f5d73" d="M45 13 24 25v21l21-11Z"/><path fill="none" stroke="#fff" stroke-width="3" stroke-linejoin="round" d="M24 2 45 13v22L24 46 3 35V13Zm0 23v21m0-21L3 13m21 12 21-12"/></svg>',
    "dashboard": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m12 3 8 4.5v9L12 21l-8-4.5v-9Z"/><path d="m4 7.5 8 4.5 8-4.5M12 12v9"/></svg>',
    "chart": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 20V10m6 10V4m6 16v-7m4 7H2"/></svg>',
    "channels": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 19V9m8 10V5m8 14v-7"/><circle cx="4" cy="7" r="2"/><circle cx="12" cy="3" r="2"/><circle cx="20" cy="10" r="2"/></svg>',
    "sun": '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M4.9 4.9l1.4 1.4m11.4 11.4 1.4 1.4M2 12h2m16 0h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>',
    "moon": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 15.5A8 8 0 0 1 8.5 4 8 8 0 1 0 20 15.5Z"/></svg>',
    "bell": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4"/></svg>',
    "power": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 2v10m5.7-6.7a9 9 0 1 1-11.4 0"/></svg>',
    "chevron-down": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg>',
    "calendar": '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="5" width="18" height="16" rx="2"/><path d="M16 3v4M8 3v4M3 10h18"/></svg>',
    "wallet": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 7h16a2 2 0 0 1 2 2v10H5a2 2 0 0 1-2-2Zm0 0 13-4v4m1 5h4"/></svg>',
    "euro": '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M16 7.5a5 5 0 1 0 0 9M6.5 10h8m-8 4h7"/></svg>',
    "users": '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="8" cy="8" r="3"/><circle cx="17" cy="8" r="3"/><path d="M2 20v-2a5 5 0 0 1 10 0v2m1-7a5 5 0 0 1 9 3v4"/></svg>',
    "target": '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="13" r="8"/><circle cx="11" cy="13" r="3"/><path d="m13 11 7-7m-4 0h4v4"/></svg>',
    "check": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m5 12 4 4L19 6"/></svg>',
    "check-circle": '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="m8 12 3 3 5-6"/></svg>',
    "trend-up": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 19V5m-6 6 6-6 6 6"/></svg>',
    "trend-down": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5v14m-6-6 6 6 6-6"/></svg>',
    "message": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M21 15a4 4 0 0 1-4 4H8l-5 3V7a4 4 0 0 1 4-4h10a4 4 0 0 1 4 4Z"/><path d="M8 10h.01M12 10h.01M16 10h.01"/></svg>',
}


def svg_icon(name: str, class_name: str = "") -> str:
    return SVG_ICONS[name].replace("<svg ", f'<svg class="svg-icon {class_name}" ')


def load_last_update() -> dict:
    """Load latest update metadata without exposing technical details."""
    if not LAST_UPDATE_PATH.exists():
        return {"status": "missing", "error": "last_update.json non trovato"}

    with LAST_UPDATE_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def as_number(series):
    import pandas as pd

    return pd.to_numeric(series.replace({"-": None, "": None}), errors="coerce")


def money(value: float | int | None) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "-"
    return f"{value:,.2f} EUR".replace(",", "X").replace(".", ",").replace("X", ".")


def integer(value: float | int | None) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "-"
    return f"{value:,.0f}".replace(",", ".")


def percent(value: float | int | None) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "-"
    return f"{value * 100:.1f}%".replace(".", ",")


def ratio(numerator: float, denominator: float) -> float | None:
    if not denominator or math.isnan(denominator):
        return None
    return numerator / denominator


def first_value(metadata: dict, keys: Iterable[str]) -> str:
    for key in keys:
        value = metadata.get(key)
        if value:
            return str(value)
    return "-"


def apply_style(st) -> None:
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Work+Sans:wght@400;500;600;700&display=swap');
        :root {
          --blue: #00a5b4;
          --blue-strong: #008faa;
          --cyan: #00a5b4;
          --orange: #ff7800;
          --green: #08a642;
          --navy: #3a4454;
          --line: #e5e7ea;
          --muted: #9da5b1;
          --page-bg: #f7f7f7;
          --sidebar-bg: #3a4454;
          --card-bg: #ffffff;
          --text-main: #3a4454;
          --text-secondary: #4f5d73;
          --border: #e5e7ea;
          --surface-muted: #f0f0f0;
          --table-header: #ffffff;
          --table-row: #ffffff;
          --table-text: #007f8b;
          --table-stripe: #f7fbfb;
          --table-hover: rgba(0,165,180,.10);
          --field-bg: #f7f7f7;
          --button-bg: rgba(0,165,180,.15);
          --table-section-border: #3a4454;
          --card-shadow: 0 5px 18px rgba(33,33,33,.07);
        }
        body:has(#dashboard-theme[data-theme="dark"]) {
          --blue: #00a5b4;
          --blue-strong: #00a5b4;
          --page-bg: #3a4454;
          --sidebar-bg: #3a4454;
          --card-bg: #282f3b;
          --text-main: #ffffff;
          --text-secondary: #c9cbcf;
          --border: rgba(157,165,177,.25);
          --line: rgba(157,165,177,.25);
          --surface-muted: #4f5d73;
          --table-header: #282f3b;
          --table-row: #282f3b;
          --table-text: #39c1cd;
          --table-stripe: #303846;
          --table-hover: rgba(0,165,180,.18);
          --field-bg: #282f3b;
          --button-bg: rgba(0,165,180,.15);
          --table-section-border: #ffffff;
          --card-shadow: 0 7px 22px rgba(0,0,0,.24);
        }
        html, body, [class*="css"], .stApp, .stApp * {
          font-family: "Work Sans", Arial, sans-serif !important;
          font-synthesis: none;
          letter-spacing: 0px !important;
          text-rendering: geometricPrecision;
          -webkit-font-smoothing: antialiased;
        }
        .font-preload { position:absolute; width:0; height:0; overflow:hidden; opacity:0; pointer-events:none; }
        .font-preload span:nth-child(1) { font-weight:400; }
        .font-preload span:nth-child(2) { font-weight:500; }
        .font-preload span:nth-child(3) { font-weight:600; }
        .font-preload span:nth-child(4) { font-weight:700; }
        .svg-icon { display:block; fill:none; stroke:currentColor; stroke-width:1.8; stroke-linecap:round; stroke-linejoin:round; shape-rendering:geometricPrecision; }
        .stApp {
          background: var(--page-bg);
          color: var(--text-main);
        }
        [data-testid="stDecoration"],
        [data-testid="stStatusWidget"],
        #MainMenu { display: none !important; }
        header[data-testid="stHeader"] {
          height: 0;
          min-height: 0;
          background: transparent !important;
        }
        [data-testid="stToolbar"] { display: none !important; }
        [data-testid="stToolbar"]:has([data-testid="stExpandSidebarButton"]) {
          display: flex !important;
          position: fixed;
          inset: 0 auto auto 0;
          width: 62px;
          height: 62px;
          padding: 10px;
          background: transparent !important;
          z-index: 1000;
          pointer-events: none;
        }
        [data-testid="stExpandSidebarButton"],
        [data-testid="stSidebarCollapseButton"] {
          display: flex !important;
          visibility: visible !important;
          color: var(--blue) !important;
        }
        [data-testid="stExpandSidebarButton"] {
          width: 42px;
          height: 42px;
          border: 1px solid var(--line);
          border-radius: 8px;
          background: #ffffff;
          box-shadow: 0 3px 14px rgba(33,33,33,.07);
          cursor: pointer;
          pointer-events: auto;
          position: relative;
          z-index: 1001;
        }
        [data-testid="stIconMaterial"] {
          font-family: "Material Symbols Rounded" !important;
          font-weight: 400 !important;
          letter-spacing: normal !important;
        }
        [data-testid="stSidebarCollapseButton"] {
          position: absolute;
          top: 12px;
          right: 10px;
          z-index: 1000;
          cursor: pointer;
          pointer-events: auto;
        }
        [data-testid="stSidebarCollapseButton"] {
          color: #ffffff !important;
        }
        [data-testid="stSidebar"] {
          width: 16.1vw !important;
          min-width: 258px !important;
          max-width: 310px !important;
          background: var(--sidebar-bg);
          border-right: 1px solid rgba(255,255,255,.08);
          overflow-x: hidden !important;
        }
        [data-testid="stSidebar"] > div:first-child { width: 16.1vw !important; min-width:258px !important; max-width:310px !important; }
        [data-testid="stSidebar"] * {
          color: #ffffff;
        }
        [data-testid="stSidebar"] [data-testid="stSidebarContent"] { padding: 0 12px !important; }
        [data-testid="stSidebar"] [data-testid="stSidebarContent"] > div { padding-top: 0 !important; }
        [data-testid="stSidebarUserContent"] { margin-top: -76px; }
        [data-testid="stSidebar"] .stSelectbox { display: none; }
        .block-container {
          max-width: none;
          padding: clamp(1px, .3vh, 3px) 1.1vw 24px 2vw;
        }
        h1, h2, h3, p {
          letter-spacing: 0px;
        }
        .brand {
          display: flex;
          align-items: center;
          gap: 19px;
          margin: 22px 0 calc(13.45vh - 79px);
          margin-left: -10px;
          margin-right: -5px;
        }
        .brand-mark {
          width: 50px;
          height: 52px;
          border-radius: 0;
          display: grid;
          place-items: center;
          background: transparent;
          color: transparent;
          box-shadow: none;
          position: relative;
          filter: drop-shadow(0 3px 8px rgba(0,210,255,.2));
        }
        .brand-mark .svg-icon { width:50px; height:50px; }
        .brand-title {
          font-size: 27px;
          font-weight: 700;
          line-height: 28px;
        }
        .brand-title span {
          color: #00a5b4;
        }
        .side-card {
          background: rgba(255,255,255,.08);
          border: 0;
          border-radius: 0;
          padding: 22px 0 2px;
          margin: 0;
          background: transparent;
          margin-left: -10px;
          margin-right: -5px;
          position: fixed;
          left: 16px;
          bottom: 4.6vh;
          width: calc(min(16.1vw, 310px) - 32px);
        }
        .account-row { display:grid; grid-template-columns:46px 1fr; align-items:center; gap:10px; }
        .avatar { width:43px; height:43px; display:grid; place-items:center; border-radius:50%; background:#fff; color:#3a4454 !important; font-size:17px; font-weight:700; line-height:20px; }
        .account-name { font-size:14px; font-weight:700; line-height:18px; }
        .account-sub { color:#c9cbcf !important; font-size:12px; font-weight:400; line-height:15px; margin-top:5px; }
        .side-nav {
          background: #00a5b4;
          border-radius: 7px;
          padding: clamp(8px, 1vh, 10px) 18px;
          font-weight: 700;
          margin: 0 0 12px;
          box-shadow: 0 10px 25px rgba(0,165,180,.2);
          margin-left: -10px;
          margin-right: -5px;
        }
        .side-nav-row {
          padding: 15px 12px;
          font-size: 16px;
          font-weight: 700;
          color: #fff;
          margin-left: -10px;
          margin-right: -5px;
        }
        .side-nav,.side-nav-row { display:flex; align-items:center; line-height:20px; }
        .nav-icon { display:inline-flex; width:30px; }
        .nav-icon .svg-icon { width:21px; height:21px; }
        .theme-toggle { position:fixed; left:20px; bottom:12.6vh; display:flex; align-items:center; gap:50px; pointer-events:none; }
        .theme-toggle .svg-icon { width:23px; height:23px; }
        [data-testid="stSidebar"] .st-key-dark_mode { position:fixed; left:47px; bottom:calc(12.6vh - 6px); width:44px; z-index:20; }
        [data-testid="stSidebar"] .st-key-dark_mode [data-testid="stWidgetLabel"] { display:none; }
        .header-actions { position:fixed; top:10px; right:34px; display:flex; gap:12px; z-index:20; }
        .header-action { position:relative; width:46px; height:46px; display:grid; place-items:center; border:1px solid var(--line); border-radius:8px; color:var(--blue); background:#fff; box-shadow:0 3px 14px rgba(33,33,33,.07); }
        .header-action .svg-icon { width:22px; height:22px; stroke-width:2; }
        .page-title {
          color: var(--blue);
          font-size: 32px;
          font-weight: 700;
          line-height: 35px;
          margin: 0 0 clamp(17px, 2.14vh, 24px);
          position: relative;
          top: 6px;
        }
        .top-filter {
          background: var(--card-bg);
          border: 1px solid var(--border);
          border-radius: 8px;
          box-shadow: 0 4px 16px rgba(33,33,33,.05);
          padding: 12px 18px;
          height: clamp(82px, 9.16vh, 99px);
          margin-bottom: clamp(12px, 1.53vh, 15px);
        }
        .label {
          color: var(--blue);
          font-size: 12px;
          font-weight: 700;
          line-height: 16px;
          margin-bottom: .35rem;
        }
        .filter-value {
          color: var(--blue-strong);
          font-size: 14px;
          font-weight: 700;
          line-height: 18px;
          height: 40px;
          display: flex;
          align-items: center;
          padding: 0 12px;
          border: 1px solid var(--line);
          border-radius: 5px;
          background: var(--field-bg);
        }
        .project-filter .filter-value { width:54%; }
        .period-filter .filter-value { width:46%; }
        .filter-value { gap:10px; }
        .filter-value .svg-icon { width:17px; height:17px; flex:0 0 auto; }
        .filter-value .chevron { margin-left:auto; }
        [data-testid="stHorizontalBlock"]:has(.filter-card-label) {
          gap: 32px;
          margin-bottom: clamp(12px, 1.53vh, 15px);
        }
        [data-testid="stHorizontalBlock"]:has(.filter-card-label) > [data-testid="stColumn"] {
          min-height: clamp(82px, 9.16vh, 99px);
          padding: 12px 18px;
          background: var(--card-bg);
          border: 1px solid var(--border);
          border-radius: 8px;
          box-shadow: 0 4px 16px rgba(33,33,33,.05);
        }
        .filter-card-label { color:var(--blue); font-size:12px; line-height:16px; font-weight:700; margin-bottom:6px; }
        [data-testid="stColumn"]:has(.project-filter-label) .stSelectbox { width:64%; }
        [data-testid="stColumn"]:has(.period-filter-label) .stDateInput { width:68%; }
        [data-testid="stColumn"]:has(.period-filter-label) [data-testid="stForm"] .stDateInput {
          width:100%;
          max-width:100%;
          min-width:0;
          box-sizing:border-box;
        }
        [data-testid="stColumn"]:has(.filter-card-label) [data-baseweb="select"] > div,
        [data-testid="stColumn"]:has(.filter-card-label) [data-baseweb="input"] > div,
        [data-testid="stColumn"]:has(.filter-card-label) input {
          background: var(--field-bg) !important;
          color: var(--blue-strong) !important;
          border-color: var(--border) !important;
          font-weight:700;
        }
        .stDateInput input {
          padding-right:40px !important;
        }
        [data-testid="stDateInput"] { position:relative; overflow:visible !important; isolation:isolate; }
        [data-testid="stDateInput"] [data-baseweb="input"] {
          position:relative;
          width:100%;
          max-width:100%;
          min-width:0;
          overflow:hidden !important;
          border-radius:8px;
          box-sizing:border-box;
        }
        [data-testid="stDateInput"] [data-baseweb="input"]:after {
          content:"";
          position:absolute;
          right:0;
          top:0;
          z-index:50;
          display:block;
          width:40px;
          height:100%;
          pointer-events:none;
          border-radius:0 8px 8px 0;
          background:#f0f0f0 center / 18px 18px no-repeat url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%233a4454' stroke-width='2.4' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='m7 9 5 5 5-5'/%3E%3C/svg%3E");
        }
        [data-testid="stForm"]:has([data-testid="stDateInput"]) [data-testid="stFormSubmitButton"] {
          padding-top:28px;
        }
        [data-testid="stForm"]:has([data-testid="stDateInput"]) [data-testid="stWidgetLabel"] p {
          color:var(--blue) !important;
          font-size:12px !important;
          line-height:16px !important;
          font-weight:600 !important;
        }
        [data-testid="stForm"]:has([data-testid="stDateInput"]) [data-testid="stFormSubmitButton"] button {
          height:40px;
          background:var(--button-bg) !important;
          border:1px solid var(--border) !important;
          color:var(--blue) !important;
          font-size:14px !important;
          line-height:18px !important;
          font-weight:600 !important;
          box-shadow:none !important;
        }
        [data-testid="stForm"]:has([data-testid="stDateInput"]) [data-testid="stFormSubmitButton"] button:hover,
        [data-testid="stForm"]:has([data-testid="stDateInput"]) [data-testid="stFormSubmitButton"] button:focus-visible {
          background:var(--surface-muted) !important;
          border-color:var(--blue) !important;
          color:var(--blue-strong) !important;
        }
        body:has(#dashboard-theme[data-theme="dark"]) [data-testid="stDateInput"] [data-baseweb="input"]:after {
          background:#4f5d73 center / 18px 18px no-repeat url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23ffffff' stroke-width='2.4' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='m7 9 5 5 5-5'/%3E%3C/svg%3E");
        }
        body:has(#dashboard-theme[data-theme="dark"]) [data-testid="stForm"]:has([data-testid="stDateInput"]) [data-testid="stFormSubmitButton"] button {
          background:#00a5b4 !important;
          border-color:#00a5b4 !important;
          color:#ffffff !important;
        }
        body:has(#dashboard-theme[data-theme="dark"]) [data-testid="stForm"]:has([data-testid="stDateInput"]) [data-testid="stFormSubmitButton"] button:hover,
        body:has(#dashboard-theme[data-theme="dark"]) [data-testid="stForm"]:has([data-testid="stDateInput"]) [data-testid="stFormSubmitButton"] button:focus-visible {
          background:#008faa !important;
          border-color:#39c1cd !important;
          color:#ffffff !important;
        }
        body:has(#dashboard-theme[data-theme="dark"]) [data-testid="stColumn"]:has(.filter-card-label) input {
          color:var(--text-main) !important;
        }
        .kpi-card {
          position: relative;
          height: clamp(140px, 15.48vh, 168px);
          margin-bottom: clamp(14px, 1.53vh, 16px);
          background: var(--card-bg);
          border: 1px solid var(--border);
          border-radius: 8px;
          box-shadow: var(--card-shadow);
          overflow: hidden;
          padding: 14px 16px 12px 99px;
        }
        .kpi-card:before {
          content: "";
          position: absolute;
          inset: 0 auto 0 0;
          width: 10px;
          background: var(--accent);
        }
        .kpi-label {
          color: var(--blue);
          font-size: 13px;
          font-weight: 700;
          line-height: 16px;
          text-transform: uppercase;
        }
        .kpi-value {
          color: var(--accent);
          font-size: 27px;
          font-weight: 700;
          margin: 12px 0 14px;
          line-height: 27px;
        }
        .kpi-note {
          color: var(--text-secondary);
          font-size: 12px;
          font-weight: 500;
          line-height: 16px;
        }
        .kpi-icon { position:absolute; left:27px; top:48px; width:43px; height:43px; display:grid; place-items:center; color:var(--accent); }
        .kpi-icon .svg-icon { width:42px; height:42px; stroke-width:1.7; }
        .panel {
          height: clamp(211px, 23.43vh, 254px);
          background: var(--card-bg);
          border: 1px solid var(--border);
          border-radius: 8px;
          box-shadow: var(--card-shadow);
          padding: 14px 31px;
        }
        .panel-title {
          color: var(--blue);
          font-size: 15px;
          font-weight: 700;
          line-height: 18px;
          text-align: center;
          text-transform: uppercase;
          margin-bottom: 8px;
        }
        .gauge {
          width: clamp(215px, 23.1vh, 250px);
          height: clamp(109px, 11.75vh, 127px);
          margin: .1rem auto .2rem;
          border-radius: 215px 215px 0 0;
          background: conic-gradient(from 270deg at 50% 100%, #00a5b4 0deg, #00a5b4 var(--angle), var(--surface-muted) var(--angle), var(--surface-muted) 180deg, transparent 180deg);
          position: relative;
        }
        .gauge:after {
          content: "";
          position: absolute;
          left: 15px;
          right: 15px;
          bottom: 0;
          height: 94px;
          border-radius: 160px 160px 0 0;
          background: #ffffff;
        }
        .gauge-value {
          color: var(--blue);
          font-size: 31px;
          font-weight: 700;
          line-height: 31px;
          text-align: center;
          margin-top: -38px;
          position: relative;
          z-index: 1;
          top: -15px;
        }
        .gauge-caption {
          color: var(--blue);
          font-size: 12px;
          font-weight: 700;
          line-height: 16px;
          text-align: center;
          position: relative;
          z-index: 1;
          top: -5px;
        }
        .gauge-target { color:var(--blue); font-size:11px; font-weight:700; line-height:14px; text-align:center; margin-top:20px; }
        .progress-row {
          margin: 25px 0 23px;
        }
        .progress-panel { position:relative; }
        .target-marker { position:absolute; left:calc(83.333% - 20.667px); top:40px; bottom:18px; z-index:3; color:#08a642; font-size:11px; font-weight:700; line-height:14px; text-align:center; transform:translateX(-50%); }
        .target-marker:before { content:""; position:absolute; top:23px; left:50%; width:0; height:0; transform:translateX(-50%); border-left:12px solid transparent; border-right:12px solid transparent; border-top:20px solid #08a642; }
        .target-marker:after { content:""; position:absolute; top:43px; bottom:0; left:50%; border-left:2px dashed #08a642; transform:translateX(-50%); }
        .progress-label {
          display: flex;
          justify-content: space-between;
          color: var(--text-main);
          font-size: 12px;
          font-weight: 700;
          line-height: 16px;
          margin-bottom: .35rem;
        }
        .bar {
          height: 31px;
          background: var(--surface-muted);
          border: 1px solid var(--border);
          border-radius: 5px;
          overflow: hidden;
        }
        .bar-fill {
          height: 100%;
          width: var(--width);
          min-width: 34px;
          max-width: 100%;
          display: flex;
          align-items: center;
          justify-content: flex-end;
          padding-right: .75rem;
          color: #ffffff;
          background: linear-gradient(90deg, #00a5b4, #008faa);
          font-weight: 700;
          font-size: 14px;
          line-height: 18px;
        }
        .efficiency {
          display: grid;
          place-items: center;
          min-height: 180px;
          position: relative;
          align-content: end;
          padding-bottom: 26px;
        }
        .efficiency:before {
          content: "";
          position: absolute;
          top: 0;
          width: clamp(238px, 25.76vh, 280px);
          height: clamp(88px, 9.6vh, 104px);
          border-radius: 50% 50% 0 0 / 100% 100% 0 0;
          background: conic-gradient(from 270deg at 50% 100%, #08a642 0 62deg, #ff9d00 62deg 118deg, #f20d18 118deg 180deg, transparent 180deg);
        }
        .efficiency:after {
          content: "";
          position: absolute;
          top: 17px;
          width: clamp(206px, 22.3vh, 246px);
          height: clamp(72px, 7.85vh, 85px);
          border-radius: 50% 50% 0 0 / 100% 100% 0 0;
          background: #fff;
        }
        .eff-value {
          color: var(--orange);
          font-size: 31px;
          font-weight: 700;
          line-height: 31px;
          position: relative;
          z-index: 2;
          top: -14px;
        }
        .eff-note {
          color: var(--text-main);
          font-size: 11px;
          font-weight: 500;
          line-height: 14px;
          text-align: center;
          position: relative;
          z-index: 2;
          top: 12px;
        }
        .needle { position:absolute; top:4px; left:50%; width:4px; height:52px; background:#008faa; border-radius:4px; transform-origin:50% 100%; transform:translateX(-50%) rotate(-8deg); z-index:3; }
        .legend-dot { display:inline-block; width:9px; height:9px; border-radius:50%; margin:0 5px 0 12px; }
        .table-title {
          color: var(--blue);
          font-size: 14px;
          font-weight: 700;
          line-height: 18px;
          margin: 17px 0 5px;
        }
        [data-testid="stDataFrame"] {
          border: 1px solid var(--line);
          border-radius: 8px;
          overflow: hidden;
          box-shadow: 0 10px 26px rgba(33,33,33,.07);
        }
        .stDownloadButton button {
          border: 1px solid var(--border);
          border-radius: 8px;
          background: #ffffff;
          color: var(--blue);
          font-weight: 700;
          line-height: 18px;
          height: 36px !important;
          min-height: 36px !important;
          white-space: nowrap;
          padding-left: 14px;
          padding-right: 14px;
        }
        .stDownloadButton button:before {
          content: "";
          width: 16px;
          height: 16px;
          background: center / 16px 16px no-repeat url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%2300a5b4' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M12 3v12m0 0 5-5m-5 5-5-5M5 21h14'/%3E%3C/svg%3E");
        }
        .stDownloadButton { position:relative; left:-9px; top:3px; width:235px; }
        .st-key-download_csv_data { margin-bottom:12px; }
        [data-testid="stHorizontalBlock"]:has(.stDownloadButton) { justify-content:flex-end; }
        [data-testid="stHorizontalBlock"]:has(.stDownloadButton) > [data-testid="stColumn"]:last-child {
          flex:0 0 235px !important;
          width:235px !important;
          min-width:235px !important;
        }
        [data-testid="stHorizontalBlock"] { gap: 16px; }
        [data-testid="stHorizontalBlock"]:has(.top-filter) { gap: 32px; }
        [data-testid="stHorizontalBlock"]:has(.kpi-card) { position:relative; left:-5px; gap:18px; width:calc(100% - 3px); }
        [data-testid="stHorizontalBlock"]:has(.panel) { position:relative; left:-9px; gap:17px; width:calc(100% + 3px); }
        [data-testid="stDataFrame"] { font-size: 11px; }
        .campaign-table-wrap { position:relative; left:-10px; top:-10px; width:calc(100% + 10px); overflow-x:auto; overflow-y:hidden; border:1px solid var(--line); border-radius:8px; background:var(--card-bg); box-shadow:0 8px 22px rgba(33,33,33,.07); scrollbar-gutter:stable; }
        .campaign-table-wrap:focus-visible { outline:3px solid rgba(0,165,180,.35); outline-offset:2px; }
        .campaign-table { width:100%; min-width:1700px; border-collapse:collapse; table-layout:fixed; font-size:12px; line-height:16px; color:var(--table-text); }
        .campaign-table th,.campaign-table td { height:40px; padding:7px 9px; border-bottom:1px solid var(--border); text-align:center; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
        .campaign-table th { height:44px; font-size:11px; font-weight:700; line-height:14px; color:#fff; white-space:normal; overflow:visible; text-overflow:clip; background:#3a4454; }
        .campaign-table td { font-weight:500; }
        .campaign-table tbody tr:not(:has(.subtotal-row-marker)):not(:has(.total-row-marker)):nth-child(even) td { background:var(--table-stripe); }
        .campaign-table tbody tr:not(:has(.subtotal-row-marker)):not(:has(.total-row-marker)):hover td { background:var(--table-hover); }
        .campaign-table th.col-funnel,.campaign-table td.col-funnel { width:120px; text-align:left; }
        .campaign-table th.col-canale,.campaign-table td.col-canale { width:90px; }
        .campaign-table th.col-campagna,.campaign-table td.col-campagna { width:300px; text-align:left; }
        .campaign-table th.col-metric,.campaign-table td.col-metric { width:105px; }
        .campaign-table th.col-action,.campaign-table td.col-action { width:245px; text-align:left; }
        .campaign-table td.col-action { white-space:normal; overflow:visible; text-overflow:clip; }
        .campaign-name { display:block; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
        .sr-only { position:absolute !important; width:1px !important; height:1px !important; padding:0 !important; margin:-1px !important; overflow:hidden !important; clip:rect(0,0,0,0) !important; white-space:nowrap !important; border:0 !important; }
        .delta-value { font-weight:700; white-space:nowrap; }
        .delta-good { color:#08a642; }
        .delta-bad { color:#e11d2e; }
        .delta-neutral { color:var(--text-secondary); }
        .action-cell { display:flex; align-items:flex-start; gap:6px; min-width:0; color:var(--text-main); font-weight:600; line-height:14px; }
        .action-cell .svg-icon { width:14px; height:14px; flex:0 0 auto; margin-top:1px; color:var(--blue); }
        .action-text { display:-webkit-box; overflow:hidden; white-space:normal; -webkit-box-orient:vertical; -webkit-line-clamp:2; }
        .campaign-table tr:last-child td { border-bottom:0; }
        [data-testid="stAppDeployButton"] { display:none !important; }
        body:has(#dashboard-theme[data-theme="dark"]) .top-filter,
        body:has(#dashboard-theme[data-theme="dark"]) .kpi-card,
        body:has(#dashboard-theme[data-theme="dark"]) .panel,
        body:has(#dashboard-theme[data-theme="dark"]) .campaign-table-wrap,
        body:has(#dashboard-theme[data-theme="dark"]) .campaign-table th,
        body:has(#dashboard-theme[data-theme="dark"]) .campaign-table td,
        body:has(#dashboard-theme[data-theme="dark"]) .stDownloadButton button {
          background: var(--card-bg) !important;
          border-color: var(--border) !important;
          color: var(--text-main) !important;
        }
        body:has(#dashboard-theme[data-theme="dark"]) .filter-value { background:var(--field-bg); border-color:var(--border); }
        body:has(#dashboard-theme[data-theme="dark"]) .kpi-note,
        body:has(#dashboard-theme[data-theme="dark"]) .progress-label,
        body:has(#dashboard-theme[data-theme="dark"]) .eff-note { color:var(--text-secondary); }
        body:has(#dashboard-theme[data-theme="dark"]) .gauge-hole { fill:var(--card-bg); }
        body:has(#dashboard-theme[data-theme="dark"]) .bar { background:var(--surface-muted); border-color:var(--border); }
        body:has(#dashboard-theme[data-theme="dark"]) .kpi-wallet .kpi-value,
        body:has(#dashboard-theme[data-theme="dark"]) .kpi-wallet .kpi-icon { color:#00a5b4; }

        .campaign-table thead th {
          background:#3a4454 !important;
          color:#fff !important;
          border-top:1px solid #3a4454 !important;
          border-bottom:2px solid #3a4454 !important;
          border-right:1px solid #3a4454 !important;
        }
        .campaign-table thead th:first-child,
        .campaign-table tbody td:first-child { border-left:1px solid #3a4454 !important; }
        .campaign-table tbody td { border-right:1px solid #3a4454 !important; }
        .campaign-table tr:has(.subtotal-row-marker) td {
          background:rgba(0,165,180,.15) !important;
          color:var(--text-main) !important;
          font-weight:700 !important;
          border-top:2px solid #3a4454 !important;
          border-bottom:2px solid #3a4454 !important;
        }
        .campaign-table tr:has(.total-row-marker) td {
          background:#3a4454 !important;
          color:#fff !important;
          font-weight:700 !important;
          border-top:2px solid #3a4454 !important;
          border-bottom:2px solid #3a4454 !important;
        }
        .campaign-table tr:has(.subtotal-row-marker) .delta-value,
        .campaign-table tr:has(.total-row-marker) .delta-value { color:inherit !important; }
        .campaign-table th.col-stima-lead,
        .campaign-table td.col-stima-lead,
        .campaign-table th.col-stima-spending,
        .campaign-table td.col-stima-spending,
        .campaign-table th.col-cpl-target,
        .campaign-table td.col-cpl-target {
          border-left:2px solid var(--table-section-border) !important;
        }
        body:has(#dashboard-theme[data-theme="dark"]) .campaign-table th.col-stima-lead,
        body:has(#dashboard-theme[data-theme="dark"]) .campaign-table td.col-stima-lead,
        body:has(#dashboard-theme[data-theme="dark"]) .campaign-table th.col-stima-spending,
        body:has(#dashboard-theme[data-theme="dark"]) .campaign-table td.col-stima-spending,
        body:has(#dashboard-theme[data-theme="dark"]) .campaign-table th.col-cpl-target,
        body:has(#dashboard-theme[data-theme="dark"]) .campaign-table td.col-cpl-target {
          border-left-color:var(--table-section-border) !important;
        }
        .subtotal-row-marker,.total-row-marker { display:none; }

        .kpi-card { display:flex; flex-direction:column; justify-content:flex-start; container-type:inline-size; }
        .kpi-value { margin:10px 0 6px; white-space:nowrap; }
        .kpi-wallet .kpi-value,.kpi-euro .kpi-value { font-size:25px; }
        .kpi-notes { min-height:43px; display:flex; flex-direction:column; justify-content:space-between; }
        .kpi-note { display:flex; align-items:center; gap:6px; color:var(--text-secondary); white-space:nowrap; }
        .kpi-note .svg-icon { width:15px; height:15px; flex:0 0 auto; stroke-width:2; }
        .kpi-note.primary { color:var(--accent); font-weight:700; }
        .kpi-note.secondary { color:var(--blue); font-weight:700; }
        .kpi-card.delta .kpi-notes { justify-content:flex-start; text-align:center; }
        .kpi-card.delta .kpi-note { justify-content:center; color:var(--orange); }
        @container (max-width: 280px) {
          .kpi-value { font-size:23px; line-height:25px; }
          .kpi-note { font-size:10px; line-height:14px; gap:4px; }
          .kpi-note .svg-icon { width:13px; height:13px; }
        }

        .svg-gauge { position:relative; width:min(100%,270px); height:166px; margin:0 auto; }
        .svg-gauge svg { display:block; width:100%; height:132px; overflow:visible; }
        .gauge-track { fill:none; stroke:var(--surface-muted); stroke-width:14; stroke-linecap:round; }
        .gauge-progress { fill:none; stroke:#00a5b4; stroke-width:14; stroke-linecap:round; }
        .gauge-needle { stroke:#008faa; stroke-width:6; stroke-linecap:round; }
        .gauge-needle-shape { fill:#008faa; }
        .gauge-pin { stroke:var(--card-bg); stroke-width:2; }
        .lead-pin { fill:#00a5b4; }
        .cpl-pin { fill:#ff9d00; }
        .svg-gauge-value { position:absolute; left:0; right:0; top:67px; text-align:center; color:var(--blue); font-size:31px; line-height:31px; font-weight:700; }
        .svg-gauge-caption { position:absolute; left:0; right:0; top:103px; text-align:center; color:var(--blue); font-size:12px; line-height:16px; font-weight:700; }
        .svg-gauge-target { position:absolute; left:0; right:0; top:145px; text-align:center; color:var(--blue); font-size:11px; line-height:14px; font-weight:700; }

        .cpl-gauge { position:relative; width:min(100%,310px); height:166px; margin:0 auto; }
        .cpl-gauge svg { display:block; width:100%; height:130px; overflow:visible; }
        .cpl-arc { fill:none; stroke-width:14; stroke-linecap:round; }
        .cpl-gauge-value { position:absolute; left:0; right:0; top:102px; text-align:center; font-size:31px; line-height:31px; font-weight:700; color:var(--eff-color); }
        .cpl-gauge .eff-note { position:absolute; left:-65px; right:-65px; top:145px; display:flex; align-items:center; justify-content:center; white-space:nowrap; color:var(--text-main); font-size:9px; line-height:13px; }

        @media (min-width: 1280px) {
          [data-testid="stSidebar"] { width:265px !important; min-width:265px !important; max-width:265px !important; }
          [data-testid="stSidebar"] > div:first-child { width:265px !important; min-width:265px !important; max-width:265px !important; }
          .period-filter .filter-value { min-width:310px; white-space:nowrap; }
          .side-card { width:233px; }
        }
        @media (min-width: 768px) and (max-width: 1279px) {
          [data-testid="stSidebar"] { width:240px !important; min-width:240px !important; }
          .side-card { width:208px; }
          .block-container { padding:12px 18px 28px; }
          [data-testid="stHorizontalBlock"]:has(.kpi-card) { flex-wrap:wrap; }
          [data-testid="stHorizontalBlock"]:has(.kpi-card) > [data-testid="stColumn"] { flex:0 0 calc(50% - 9px) !important; width:calc(50% - 9px) !important; }
          [data-testid="stHorizontalBlock"]:has(.panel) { flex-wrap:wrap; }
          [data-testid="stHorizontalBlock"]:has(.panel) > [data-testid="stColumn"] { flex:0 0 100% !important; width:100% !important; }
          .panel { height:245px; margin-bottom:14px; }
          .project-filter .filter-value,.period-filter .filter-value { width:100%; }
          [data-testid="stColumn"]:has(.filter-card-label) .stSelectbox,
          [data-testid="stColumn"]:has(.filter-card-label) .stDateInput { width:100%; }
          .campaign-table-wrap { overflow-x:auto; }
          .campaign-table { min-width:1700px; }
        }
        @media (max-width: 767px) {
          [data-testid="stSidebar"] { width:250px !important; min-width:250px !important; }
          .side-card { width:218px; }
          .block-container { padding:12px 14px 28px; }
          .page-title { font-size:25px; line-height:30px; margin-right:90px; }
          .header-actions { right:12px; gap:7px; }
          .header-action { width:39px; height:39px; }
          [data-testid="stHorizontalBlock"]:has(.top-filter),
          [data-testid="stHorizontalBlock"]:has(.filter-card-label),
          [data-testid="stHorizontalBlock"]:has(.kpi-card),
          [data-testid="stHorizontalBlock"]:has(.panel),
          [data-testid="stHorizontalBlock"]:has(.table-title) { flex-wrap:wrap; gap:10px; left:0; width:100%; }
          [data-testid="stHorizontalBlock"]:has(.top-filter) > [data-testid="stColumn"],
          [data-testid="stHorizontalBlock"]:has(.filter-card-label) > [data-testid="stColumn"],
          [data-testid="stHorizontalBlock"]:has(.kpi-card) > [data-testid="stColumn"],
          [data-testid="stHorizontalBlock"]:has(.panel) > [data-testid="stColumn"],
          [data-testid="stHorizontalBlock"]:has(.table-title) > [data-testid="stColumn"] { flex:0 0 100% !important; width:100% !important; }
          .top-filter { height:auto; min-height:82px; margin-bottom:0; }
          .project-filter .filter-value,.period-filter .filter-value { width:100%; }
          [data-testid="stHorizontalBlock"]:has(.filter-card-label) { margin-bottom:10px; }
          [data-testid="stHorizontalBlock"]:has(.filter-card-label) > [data-testid="stColumn"] { min-height:82px; }
          [data-testid="stColumn"]:has(.filter-card-label) .stSelectbox,
          [data-testid="stColumn"]:has(.filter-card-label) .stDateInput { width:100%; }
          .period-filter .filter-value { white-space:nowrap; font-size:12px; }
          .kpi-card { height:145px; margin-bottom:0; }
          .panel { height:235px; margin-bottom:0; padding:14px 18px; }
          .target-marker { left:calc(83.333% - 12px); bottom:14px; }
          .stDownloadButton { left:0; top:0; width:100%; }
          [data-testid="stHorizontalBlock"]:has(.stDownloadButton) > [data-testid="stColumn"]:last-child {
            flex:0 0 100% !important;
            width:100% !important;
            min-width:0 !important;
          }
          .campaign-table-wrap { left:0; top:0; width:100%; overflow-x:auto; }
          .campaign-table { min-width:1700px; }
          .cpl-gauge .eff-note { left:-10px; right:-10px; font-size:8px; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_project_tooltips(components, selected_project: str) -> None:
    selected_json = json.dumps(str(selected_project))
    components.html(
        fr"""
        <script>
        (() => {{
          const host = window.parent;
          const doc = host.document;
          const selectedProject = {selected_json};

          const applyTitles = () => {{
            const projectSelect = doc.querySelector('.st-key-project_filter [data-baseweb="select"]');
            if (projectSelect) projectSelect.setAttribute('title', selectedProject);

            doc.querySelectorAll('[role="option"]').forEach((option) => {{
              const label = option.textContent.replace(/\s+/g, ' ').trim();
              if (!label) return;
              option.setAttribute('title', label);
              option.querySelectorAll('*').forEach((child) => child.setAttribute('title', label));
            }});
          }};

          if (host.__dynamicaProjectTooltipObserver) {{
            host.__dynamicaProjectTooltipObserver.disconnect();
          }}
          const observer = new MutationObserver(applyTitles);
          observer.observe(doc.body, {{ childList: true, subtree: true }});
          host.__dynamicaProjectTooltipObserver = observer;
          applyTitles();
        }})();
        </script>
        """,
        height=0,
        width=0,
    )


def render_sidebar(st, df):
    st.sidebar.markdown(
        f"""
        <div class="brand">
          <div class="brand-mark">{svg_icon("logo")}</div>
          <div class="brand-title">Dynamica<br><span>Retail</span></div>
        </div>
        <div class="side-nav"><span class="nav-icon">{svg_icon("dashboard")}</span>Dashboard</div>
        <div class="theme-toggle">{svg_icon("sun")}{svg_icon("moon")}</div>
        """,
        unsafe_allow_html=True,
    )
    st.sidebar.toggle("Tema scuro", key="dark_mode")

    def options(column: str) -> list[str]:
        values = sorted(str(value) for value in df[column].dropna().unique())
        return ["Tutti"] + values

    funnel = st.sidebar.selectbox("Funnel", options("funnel"))
    platform = st.sidebar.selectbox("Piattaforma", options("platform"))
    channel = st.sidebar.selectbox("Canale", options("channel"))
    campaign = st.sidebar.selectbox("Campagna", options("campaign_name"))

    st.sidebar.markdown(
        f"""
        <div class="side-card">
          <div class="account-row"><div class="avatar">DR</div><div><div class="account-name">Dynamica Retail</div><div class="account-sub">Client account</div></div></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    filtered = df.copy()
    for column, selected in {
        "funnel": funnel,
        "platform": platform,
        "channel": channel,
        "campaign_name": campaign,
    }.items():
        if selected != "Tutti":
            filtered = filtered[filtered[column].astype(str) == selected]
    return filtered


def render_kpi_card(
    st,
    label: str,
    value: str,
    primary_note: str,
    secondary_note: str,
    color: str,
    primary_icon: str | None = None,
    secondary_icon: str | None = None,
) -> None:
    icon_name = {
        "Speso totale": "wallet",
        "Delta speso": "euro",
        "Lead effettive": "users",
        "CPL medio": "target",
    }[label]
    st.markdown(
        f"""
        <div class="kpi-card kpi-{icon_name} {'delta' if label == 'Delta speso' else ''}" style="--accent:{color}">
          <div class="kpi-icon">{svg_icon(icon_name)}</div>
          <div class="kpi-label">{label}</div>
          <div class="kpi-value">{value}</div>
          <div class="kpi-notes">
            <div class="kpi-note primary">{svg_icon(primary_icon) if primary_icon else ''}<span>{primary_note}</span></div>
            <div class="kpi-note secondary">{svg_icon(secondary_icon) if secondary_icon else ''}<span>{secondary_note or '&nbsp;'}</span></div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def prepare_data(pd) -> "pd.DataFrame":
    if not DATA_PATH.exists():
        return pd.DataFrame()

    df = pd.read_csv(DATA_PATH)
    numeric_columns = [
        "investimento_media",
        "stima_lead_progressiva",
        "lead_effettive",
        "delta_lead",
        "stima_spending_progressiva",
        "speso_effettivo",
        "delta_speso",
        "delta_delivery_pct",
        "cpl_target",
        "cpl_effettivo",
        "delta_cpl",
        "kpi_investimento_media_totale",
        "kpi_stima_spending_progressiva_totale",
        "kpi_speso_effettivo_totale",
        "kpi_delta_speso_totale",
        "kpi_delta_delivery_pct_totale",
        "kpi_lead_effettive_totale",
        "kpi_stima_lead_progressiva_totale",
        "kpi_delta_lead_totale",
        "kpi_cpl_effettivo_totale",
        "kpi_cpl_target_totale",
        "kpi_delta_cpl_totale",
    ]
    numeric_columns.extend(
        column
        for column in df.columns
        if column.startswith("kpi_") or column.startswith("subtotal_")
    )
    for column in numeric_columns:
        if column in df.columns:
            df[column] = as_number(df[column])
    if "campaign_name" in df.columns:
        df = df[
            ~df["campaign_name"].fillna("").astype(str).str.casefold().isin(
                EXCLUDED_CAMPAIGN_NAMES
            )
        ].copy()
    if "meta_campaign_id" in df.columns:
        meta_ids = df["meta_campaign_id"].fillna("").astype(str).str.replace(
            r"\.0$", "", regex=True
        )
        df = df[~meta_ids.isin(EXCLUDED_CAMPAIGN_IDS)].copy()
    return df


def prepare_spend_daily(pd) -> "pd.DataFrame":
    """Load privacy-safe daily spend and CRM lead aggregates."""
    if not REPORT_DAILY_PATH.exists():
        return pd.DataFrame(
            columns=[
                "date", "source", "excel_row", "spend_rollup_excel_row", "campaign_id",
                "campaign_name", "spend", "leads", "monthly_lead_target",
                "lead_allocation_method",
            ]
        )
    daily = pd.read_csv(
        REPORT_DAILY_PATH,
        dtype={
            "campaign_id": "string", "excel_row": "string",
            "spend_rollup_excel_row": "string",
        },
    )
    daily["date"] = pd.to_datetime(daily["date"], errors="coerce").dt.date
    daily["spend"] = pd.to_numeric(daily.get("spend"), errors="coerce")
    daily["leads"] = (
        pd.to_numeric(daily["leads"], errors="coerce")
        if "leads" in daily else pd.NA
    )
    daily["monthly_lead_target"] = (
        pd.to_numeric(daily["monthly_lead_target"], errors="coerce")
        if "monthly_lead_target" in daily else pd.NA
    )
    daily["campaign_id"] = daily["campaign_id"].fillna("").astype(str).str.strip()
    excluded = (
        daily["campaign_name"].fillna("").astype(str).str.casefold().isin(
            EXCLUDED_CAMPAIGN_NAMES
        )
        | daily["campaign_id"].isin(EXCLUDED_CAMPAIGN_IDS)
    )
    return daily.loc[~excluded].dropna(subset=["date"])


def add_unmapped_daily_campaigns(pd, report_df, daily_df):
    """Add active API campaigns missing from the Sheet without inventing lead data."""
    if daily_df.empty:
        return report_df

    def clean_id(value) -> str:
        if pd.isna(value):
            return ""
        text = str(value).strip()
        return text[:-2] if text.endswith(".0") else text

    configured = {
        "google_ads": {
            clean_id(value) for value in report_df.get("google_campaign_id", [])
            if clean_id(value)
        },
        "meta_ads": {
            clean_id(value) for value in report_df.get("meta_campaign_id", [])
            if clean_id(value)
        },
    }
    totals = (
        daily_df.groupby(["source", "campaign_id", "campaign_name"], dropna=False)["spend"]
        .sum()
        .reset_index()
    )
    additions = []
    for row in totals.itertuples(index=False):
        if (
            row.source not in {"google_ads", "meta_ads"}
            or pd.isna(row.spend)
            or float(row.spend or 0) <= 0
            or row.campaign_id in configured.get(row.source, set())
            or row.campaign_id in EXCLUDED_CAMPAIGN_IDS
            or str(row.campaign_name or "").casefold() in EXCLUDED_CAMPAIGN_NAMES
        ):
            continue
        new_row = {column: None for column in report_df.columns}
        new_row.update(
            {
                "funnel": "API Ads",
                "platform": "Google" if row.source == "google_ads" else "Meta",
                "channel": "API",
                "campaign_name": row.campaign_name,
                "google_campaign_id": row.campaign_id if row.source == "google_ads" else None,
                "meta_campaign_id": row.campaign_id if row.source == "meta_ads" else None,
                "source_status": f"{row.source}:daily_only",
            }
        )
        additions.append(new_row)
    if not additions:
        return report_df
    return pd.concat([report_df, pd.DataFrame(additions)], ignore_index=True)


def load_spend_daily_status() -> dict:
    if not REPORT_DAILY_STATUS_PATH.exists():
        return {}
    try:
        with REPORT_DAILY_STATUS_PATH.open("r", encoding="utf-8") as stream:
            return json.load(stream)
    except (OSError, json.JSONDecodeError):
        return {}


def normalize_period(selected_period, fallback_start, fallback_end):
    if isinstance(selected_period, (tuple, list)):
        if len(selected_period) == 2:
            start, end = selected_period
        elif len(selected_period) == 1:
            start = end = selected_period[0]
        else:
            start, end = fallback_start, fallback_end
    else:
        start = end = selected_period or fallback_end
    if start > end:
        raise ValueError("La data iniziale non può essere successiva alla data finale.")
    if (start.year, start.month) != (end.year, end.month):
        raise ValueError("Data iniziale e data finale devono appartenere allo stesso mese.")
    return start, end


def apply_daily_spend_filter(pd, report_df, daily_df, start_date, end_date):
    """Apply daily Ads spend and CRM lead aggregates to the selected interval."""
    from calendar import monthrange
    import re
    from src.report_groups import client_subtotal_group
    from src.dates import weekdays_inclusive, weekdays_in_month

    if daily_df.empty:
        return report_df.copy()
    filtered_daily = daily_df[
        (daily_df["date"] >= start_date) & (daily_df["date"] <= end_date)
    ].copy()
    ads_daily = filtered_daily[
        filtered_daily["source"].isin(["google_ads", "meta_ads"])
    ].copy()
    totals = ads_daily.groupby(["source", "campaign_id"], dropna=False)["spend"].sum()
    result = report_df.copy()
    selected_days = (end_date - start_date).days + 1
    days_in_month = monthrange(start_date.year, start_date.month)[1]
    dem_selected_days = weekdays_inclusive(start_date, end_date)
    dem_days_in_month = weekdays_in_month(start_date)

    def clean_id(value) -> str:
        if pd.isna(value):
            return ""
        text = str(value).strip()
        return text[:-2] if text.endswith(".0") else text

    has_spend_rollup = "spend_rollup_excel_row" in ads_daily.columns
    spend_by_excel_row: dict[str, float] = {}
    rolled_source_rows: set[str] = set()
    if has_spend_rollup:
        ads_daily["excel_row"] = ads_daily.get("excel_row", "").map(clean_id)
        ads_daily["spend_rollup_excel_row"] = ads_daily[
            "spend_rollup_excel_row"
        ].map(clean_id)
        mapped_spend = ads_daily[ads_daily["spend_rollup_excel_row"] != ""]
        spend_by_excel_row = (
            mapped_spend.groupby("spend_rollup_excel_row")["spend"].sum().to_dict()
        )
        rolled_source_rows = set(
            mapped_spend.loc[
                mapped_spend["excel_row"]
                != mapped_spend["spend_rollup_excel_row"],
                "excel_row",
            ]
        )

    leads_available = "leads" in filtered_daily.columns
    if leads_available:
        crm = filtered_daily[
            filtered_daily["source"].isin(["crm", "crm_area_clienti"])
        ].copy()
        crm["leads"] = pd.to_numeric(crm["leads"], errors="coerce").fillna(0)
        crm["excel_row"] = crm.get("excel_row", "").map(clean_id)
        normal_counts = (
            crm[crm["source"] == "crm"]
            .groupby("excel_row", dropna=False)["leads"]
            .sum()
            .to_dict()
        )
        area_total = int(
            crm.loc[crm["source"] == "crm_area_clienti", "leads"].sum()
        )
        area_indexes = sorted(
            [
                index
                for index, row in result.iterrows()
                if client_subtotal_group(row.to_dict()) == "area_clienti"
                and clean_id(row.get("excel_row"))
            ],
            key=lambda index: int(float(result.at[index, "excel_row"])),
        )
        dynamic_leads: dict[int, float | None] = {}
        for index, row in result.iterrows():
            excel_row = clean_id(row.get("excel_row"))
            if not excel_row:
                dynamic_leads[index] = None
            elif index in area_indexes:
                dynamic_leads[index] = None
            else:
                dynamic_leads[index] = float(normal_counts.get(excel_row, 0))
        result["lead_effettive"] = pd.Series(dynamic_leads)
        if "stima_lead" in result:
            result["stima_lead_giornaliere"] = (
                pd.to_numeric(result["stima_lead"], errors="coerce") / days_in_month
            )
            result["stima_lead_progressiva"] = (
                result["stima_lead_giornaliere"] * selected_days
            )
        result["delta_lead"] = (
            pd.to_numeric(result["lead_effettive"], errors="coerce")
            - pd.to_numeric(result.get("stima_lead_progressiva"), errors="coerce")
        )

    dynamic_values: dict[int, float | None] = {}
    for index, row in result.iterrows():
        platform = str(row.get("platform") or "").casefold()
        excel_row = clean_id(row.get("excel_row"))
        if "google" in platform:
            key = ("google_ads", clean_id(row.get("google_campaign_id")))
        elif "meta" in platform:
            key = ("meta_ads", clean_id(row.get("meta_campaign_id")))
        else:
            is_dem = client_subtotal_group(row.to_dict()) == "dem"
            lead_value = pd.to_numeric(
                pd.Series([row.get("lead_effettive")]), errors="coerce"
            ).iloc[0]
            cpl_value = pd.to_numeric(
                pd.Series([row.get("cpl_target")]), errors="coerce"
            ).iloc[0]
            dynamic_values[index] = (
                float(lead_value * cpl_value)
                if leads_available and is_dem
                and not pd.isna(lead_value) and not pd.isna(cpl_value)
                else row.get("speso_effettivo")
            )
            continue
        if has_spend_rollup and excel_row:
            dynamic_values[index] = (
                None
                if excel_row in rolled_source_rows
                else float(spend_by_excel_row.get(excel_row, 0.0))
            )
        else:
            dynamic_values[index] = float(totals.get(key, 0.0)) if key[1] else 0.0

    # Preserve the existing continuation-row rollup used by report_data.csv.
    excel_row_to_index = {
        clean_id(row.get("excel_row")): index for index, row in result.iterrows()
    }
    for index, row in result.iterrows():
        match = re.search(r"rolled_up_to_excel_row_(\d+)", str(row.get("source_status") or ""))
        if not match:
            continue
        parent_index = excel_row_to_index.get(match.group(1))
        if parent_index is not None:
            dynamic_values[parent_index] = float(dynamic_values.get(parent_index) or 0) + float(dynamic_values.get(index) or 0)
        dynamic_values[index] = None

    result["speso_effettivo"] = pd.Series(dynamic_values)
    if "investimento_media" in result:
        investment = pd.to_numeric(result["investimento_media"], errors="coerce")
        is_dem = result.apply(
            lambda row: client_subtotal_group(row.to_dict()) == "dem", axis=1
        )
        result["stima_spending_progressiva"] = investment / days_in_month * selected_days
        result.loc[is_dem, "stima_spending_progressiva"] = (
            investment.loc[is_dem] / dem_days_in_month * dem_selected_days
        )
        result["stima_spending_giornaliera"] = investment / days_in_month
        result.loc[is_dem, "stima_spending_giornaliera"] = (
            investment.loc[is_dem] / dem_days_in_month
        )
    result["delta_speso"] = result["speso_effettivo"] - result["stima_spending_progressiva"]
    result["delta_delivery_pct"] = result["delta_speso"] / result["stima_spending_progressiva"].replace(0, pd.NA)
    if leads_available:
        result["cpl_effettivo"] = (
            pd.to_numeric(result["speso_effettivo"], errors="coerce")
            / pd.to_numeric(result["lead_effettive"], errors="coerce").replace(0, pd.NA)
        )
        result["delta_cpl"] = (
            result["cpl_effettivo"]
            - pd.to_numeric(result.get("cpl_target"), errors="coerce")
        )
    from src.combined_campaigns import apply_combined_campaign_metrics

    combined_records = apply_combined_campaign_metrics(result.to_dict("records"))
    result = pd.DataFrame(combined_records, columns=result.columns)
    _update_dynamic_spend_summaries(pd, result)
    return result


def _update_dynamic_spend_summaries(pd, frame) -> None:
    """Align official Excel spending totals/subtotals with the selected period."""
    from src.report_groups import CLIENT_GROUPS, client_subtotal_group

    def summary_values(group):
        planned = pd.to_numeric(
            group.get("stima_spending_progressiva"), errors="coerce"
        )
        spent = pd.to_numeric(group.get("speso_effettivo"), errors="coerce")
        planned_total = (
            None if planned is None or not planned.notna().any()
            else float(planned.sum(min_count=1))
        )
        spent_total = (
            None if spent is None or not spent.notna().any()
            else float(spent.sum(min_count=1))
        )
        delta = (
            spent_total - planned_total
            if spent_total is not None and planned_total is not None else None
        )
        delivery = (
            delta / planned_total
            if delta is not None and planned_total not in (None, 0) else None
        )
        return {
            "stima_spending_progressiva": planned_total,
            "speso_effettivo": spent_total,
            "delta_speso": delta,
            "delta_delivery_pct": delivery,
        }

    total = summary_values(frame)
    for field, value in total.items():
        frame[f"kpi_{field}_totale"] = value

    group_labels = frame.apply(
        lambda row: client_subtotal_group(row.to_dict()), axis=1
    )
    for slug, _label in CLIENT_GROUPS:
        subtotal = summary_values(frame[group_labels == slug])
        for field, value in subtotal.items():
            frame[f"subtotal_{slug}_{field}"] = value


def build_period_report_frame(
    pd, report_df, daily_df, selected_start, selected_end
):
    """Return campaign plus official summary rows for the selected dates."""
    from calendar import monthrange
    from src.build_report_data import _summary_row
    from src.report_groups import CLIENT_GROUPS, client_subtotal_group

    report_start = pd.to_datetime(report_df["start_date"], errors="coerce").dt.date
    report_end = pd.to_datetime(report_df["end_date"], errors="coerce").dt.date
    if (
        report_start.notna().any()
        and report_end.notna().any()
        and selected_start == report_start.dropna().iloc[0]
        and selected_end == report_end.dropna().iloc[0]
        and "row_type" in report_df.columns
    ):
        return report_df.copy()

    campaigns = (
        report_df.copy()
        if "row_type" not in report_df.columns
        else report_df[report_df["row_type"].fillna("campaign") == "campaign"].copy()
    )
    dynamic = apply_daily_spend_filter(
        pd, campaigns, daily_df, selected_start, selected_end
    )
    dynamic["row_type"] = "campaign"
    dynamic["start_date"] = selected_start.isoformat()
    dynamic["end_date"] = selected_end.isoformat()
    days = (selected_end - selected_start).days + 1
    days_in_month = monthrange(selected_start.year, selected_start.month)[1]
    official = (
        report_df[report_df["row_type"].isin(["subtotal", "total"])].copy()
        if "row_type" in report_df.columns else report_df.iloc[0:0].copy()
    )

    summaries: list[dict] = []
    selected_daily = daily_df[
        (daily_df["date"] >= selected_start) & (daily_df["date"] <= selected_end)
    ]
    area_total = None
    if {"source", "leads"}.issubset(selected_daily.columns):
        area_total = float(pd.to_numeric(
            selected_daily.loc[
                selected_daily["source"] == "crm_area_clienti", "leads"
            ], errors="coerce"
        ).fillna(0).sum())
    for slug, label in CLIENT_GROUPS:
        group = dynamic[
            dynamic.apply(
                lambda row: client_subtotal_group(row.to_dict()) == slug, axis=1
            )
        ]
        if group.empty:
            continue
        summary = _summary_row(
            group.to_dict("records"), f"TOT {label}", "subtotal"
        )
        if slug == "area_clienti" and area_total is not None:
            summary["lead_effettive"] = area_total
        source = official[official["funnel"].astype(str) == f"TOT {label}"]
        if len(source.index) == 1:
            source_row = source.iloc[0]
            for field in (
                "stima_pratiche", "stima_lead", "cpp_medio", "cpl_target"
            ):
                if pd.isna(summary.get(field)):
                    value = pd.to_numeric(
                        pd.Series([source_row.get(field)]), errors="coerce"
                    ).iloc[0]
                    summary[field] = None if pd.isna(value) else float(value)
        if summary.get("stima_lead") is None and "monthly_lead_target" in daily_df:
            planning = daily_df[
                (daily_df["source"] == "planning")
                & (daily_df["campaign_name"].astype(str) == f"TOT {label}")
            ]
            target = pd.to_numeric(
                planning["monthly_lead_target"], errors="coerce"
            ).dropna()
            if not target.empty:
                summary["stima_lead"] = float(target.iloc[0])
        lead_target = summary.get("stima_lead")
        if lead_target is not None:
            summary["stima_lead_giornaliere"] = lead_target / days_in_month
            summary["stima_lead_progressiva"] = (
                summary["stima_lead_giornaliere"] * days
            )
            summary["delta_lead"] = (
                summary["lead_effettive"] - summary["stima_lead_progressiva"]
                if summary.get("lead_effettive") is not None else None
            )
        if slug == "area_clienti" and area_total is not None:
            summary["cpl_effettivo"] = (
                summary.get("speso_effettivo") / area_total
                if area_total and summary.get("speso_effettivo") is not None
                else None
            )
            summary["delta_cpl"] = (
                summary["cpl_effettivo"] - summary["cpl_target"]
                if summary.get("cpl_effettivo") is not None
                and summary.get("cpl_target") is not None else None
            )
        summary["start_date"] = selected_start.isoformat()
        summary["end_date"] = selected_end.isoformat()
        summaries.append(summary)

    total = _summary_row(
        dynamic.to_dict("records"), "TOTALE GENERALE", "total"
    )
    subtotal_leads = [summary.get("lead_effettive") for summary in summaries]
    total["lead_effettive"] = (
        sum(float(value) for value in subtotal_leads if value is not None)
        if any(value is not None for value in subtotal_leads) else None
    )
    for field in ("stima_pratiche", "stima_lead", "stima_lead_giornaliere"):
        values = [summary.get(field) for summary in summaries]
        total[field] = (
            sum(float(value) for value in values if value is not None)
            if any(value is not None for value in values) else None
        )
    if total.get("stima_lead_giornaliere") is not None:
        total["stima_lead_progressiva"] = total["stima_lead_giornaliere"] * days
        total["delta_lead"] = (
            total["lead_effettive"] - total["stima_lead_progressiva"]
            if total.get("lead_effettive") is not None else None
        )
    if total.get("investimento_media") is not None and total.get("stima_lead"):
        total["cpl_target"] = total["investimento_media"] / total["stima_lead"]
    if total.get("speso_effettivo") is not None and total.get("lead_effettive"):
        total["cpl_effettivo"] = total["speso_effettivo"] / total["lead_effettive"]
    total["delta_cpl"] = (
        total["cpl_effettivo"] - total["cpl_target"]
        if total.get("cpl_effettivo") is not None
        and total.get("cpl_target") is not None else None
    )
    total["start_date"] = selected_start.isoformat()
    total["end_date"] = selected_end.isoformat()
    return pd.concat(
        [dynamic, pd.DataFrame([*summaries, total])],
        ignore_index=True,
        sort=False,
    )


def prepare_excel_export_frame(
    pd, report_df, daily_df, metadata: dict, selected_start, selected_end
):
    """Create the all-campaign DataFrame represented by the selected date range."""
    report_start = pd.to_datetime(metadata.get("start_date"), errors="coerce")
    report_end = pd.to_datetime(metadata.get("end_date"), errors="coerce")
    selected_is_report_period = (
        not pd.isna(report_start)
        and not pd.isna(report_end)
        and selected_start == report_start.date()
        and selected_end == report_end.date()
    )
    if selected_is_report_period and "row_type" in report_df.columns:
        export_df = report_df.copy()
        export_df.attrs["metadata"] = dict(metadata)
        return export_df

    if daily_df.empty:
        if not selected_is_report_period:
            raise ValueError(
                "I dati giornalieri di spesa non sono disponibili per il periodo selezionato."
            )

    export_df = build_period_report_frame(
        pd, report_df, daily_df, selected_start, selected_end
    )
    export_metadata = dict(metadata)
    export_metadata["start_date"] = selected_start.isoformat()
    export_metadata["end_date"] = selected_end.isoformat()
    export_df["start_date"] = selected_start.isoformat()
    export_df["end_date"] = selected_end.isoformat()
    export_df.attrs["metadata"] = export_metadata
    return export_df


def build_excel_download(
    pd, report_df, daily_df, metadata: dict, selected_start, selected_end
) -> tuple[bytes, str]:
    """Generate an XLSX snapshot for the current dates without replacing latest."""
    from src.update_excel import generate_client_excel

    export_df = prepare_excel_export_frame(
        pd, report_df, daily_df, metadata, selected_start, selected_end
    )
    with TemporaryDirectory(prefix="dynamica_excel_") as output_dir:
        generated_path = Path(
            generate_client_excel(export_df, output_dir=output_dir)
        )
        content = generated_path.read_bytes()
    filename = (
        f"Report_Dynamica_{selected_start:%Y-%m-%d}_{selected_end:%Y-%m-%d}.xlsx"
    )
    return content, filename


def _dashboard_numeric_series(pd, frame, column: str):
    if column not in frame.columns:
        return pd.Series(dtype="float64")
    return pd.to_numeric(frame[column], errors="coerce").dropna()


def _dashboard_aggregate_summary(pd, static_frame, dynamic_frame) -> dict:
    """Aggregate only the rows currently represented by dashboard filters."""
    def total(frame, column: str):
        values = _dashboard_numeric_series(pd, frame, column)
        return None if values.empty else float(values.sum())

    lead_plan = total(static_frame, "stima_lead_progressiva")
    leads = total(static_frame, "lead_effettive")
    delta_lead = total(static_frame, "delta_lead")
    planned_spend = total(dynamic_frame, "stima_spending_progressiva")
    spent = total(dynamic_frame, "speso_effettivo")
    delta_spend = (
        spent - planned_spend
        if spent is not None and planned_spend is not None else None
    )
    cpl_targets = _dashboard_numeric_series(pd, static_frame, "cpl_target")
    cpl_target = None if cpl_targets.empty else float(cpl_targets.mean())
    cpl_effective = (
        spent / leads
        if spent is not None and leads not in (None, 0) else None
    )
    delta_cpl = (
        cpl_effective - cpl_target
        if cpl_effective is not None and cpl_target is not None else None
    )
    return {
        "stima_lead_progressiva": lead_plan,
        "lead_effettive": leads,
        "delta_lead": delta_lead,
        "stima_spending_progressiva": planned_spend,
        "speso_effettivo": spent,
        "delta_speso": delta_spend,
        "cpl_target": cpl_target,
        "cpl_effettivo": cpl_effective,
        "delta_cpl": delta_cpl,
    }


def _dashboard_official_summary(
    pd, frame, fallback: dict, *, slug: str | None = None
) -> dict:
    values = {}
    for field in DASHBOARD_SUMMARY_FIELDS:
        column = (
            f"kpi_{field}_totale"
            if slug is None else f"subtotal_{slug}_{field}"
        )
        official = _dashboard_numeric_series(pd, frame, column)
        values[field] = (
            fallback.get(field) if official.empty else float(official.iloc[0])
        )
    return values


def build_dashboard_table_frame(
    pd,
    static_frame,
    dynamic_frame,
    all_frame,
    *,
    full_scope: bool,
):
    """Use campaign rows plus the official summary rows already in the report."""
    from src.report_groups import CLIENT_GROUPS, client_subtotal_group

    if dynamic_frame.empty:
        return pd.DataFrame(columns=[*DASHBOARD_TABLE_COLUMNS, "_row_type"])

    if "row_type" not in all_frame.columns:
        dynamic_groups = dynamic_frame.apply(
            lambda row: client_subtotal_group(row.to_dict()), axis=1
        )
        all_groups = all_frame.apply(
            lambda row: client_subtotal_group(row.to_dict()), axis=1
        )
        output_rows: list[dict] = []
        summaries: list[tuple[dict, bool]] = []
        for slug, label in CLIENT_GROUPS:
            group = dynamic_frame[dynamic_groups == slug]
            if group.empty:
                continue
            static_group = static_frame.reindex(group.index)
            fallback = _dashboard_aggregate_summary(pd, static_group, group)
            complete = set(group.index) == set(all_frame[all_groups == slug].index)
            summary = (
                _dashboard_official_summary(pd, group, fallback, slug=slug)
                if full_scope or complete else fallback
            )
            for _, campaign in group.iterrows():
                campaign_row = campaign.to_dict()
                campaign_row["_row_type"] = "campaign"
                output_rows.append(campaign_row)
            subtotal = {column: None for column in DASHBOARD_TABLE_COLUMNS}
            subtotal.update(summary)
            subtotal["funnel"] = f"TOT {label}"
            subtotal["_row_type"] = "subtotal"
            output_rows.append(subtotal)
            summaries.append((summary, complete))
        fallback = _dashboard_aggregate_summary(pd, static_frame, dynamic_frame)
        if full_scope:
            summary = _dashboard_official_summary(pd, dynamic_frame, fallback)
        elif len(summaries) == 1 and summaries[0][1]:
            summary = dict(summaries[0][0])
        else:
            summary = fallback
        total = {column: None for column in DASHBOARD_TABLE_COLUMNS}
        total.update(summary)
        total["funnel"] = "TOTALE GENERALE"
        total["_row_type"] = "total"
        output_rows.append(total)
        return pd.DataFrame(output_rows)

    campaigns = (
        dynamic_frame.copy()
        if "row_type" not in dynamic_frame.columns
        else dynamic_frame[dynamic_frame["row_type"].fillna("campaign") == "campaign"].copy()
    )
    all_campaigns = all_frame[
        all_frame["row_type"].fillna("campaign") == "campaign"
    ].copy()
    dynamic_groups = campaigns.apply(
        lambda row: client_subtotal_group(row.to_dict()), axis=1
    )
    all_groups = all_campaigns.apply(
        lambda row: client_subtotal_group(row.to_dict()), axis=1
    )
    output_rows: list[dict] = []

    def identities(frame):
        return {
            (
                str(row.get("excel_row") or ""),
                str(row.get("campaign_name") or ""),
            )
            for _, row in frame.iterrows()
        }

    for slug, label in CLIENT_GROUPS:
        group = campaigns[dynamic_groups == slug]
        if group.empty:
            continue

        for _, campaign in group.iterrows():
            campaign_row = campaign.to_dict()
            campaign_row["_row_type"] = "campaign"
            output_rows.append(campaign_row)

        complete = identities(group) == identities(all_campaigns[all_groups == slug])
        official = all_frame[
            (all_frame.get("row_type", "") == "subtotal")
            & (all_frame["funnel"].astype(str) == f"TOT {label}")
        ]
        if complete and not official.empty:
            subtotal_row = official.iloc[0].to_dict()
        else:
            static_group = static_frame.reindex(group.index)
            subtotal_row = {column: None for column in DASHBOARD_TABLE_COLUMNS}
            subtotal_row.update(
                _dashboard_aggregate_summary(pd, static_group, group)
            )
            subtotal_row["funnel"] = f"TOT {label}"
        subtotal_row["_row_type"] = "subtotal"
        output_rows.append(subtotal_row)

    complete_total = identities(campaigns) == identities(all_campaigns)
    official_total = all_frame[all_frame.get("row_type", "") == "total"]
    if complete_total and not official_total.empty:
        total_row = official_total.iloc[0].to_dict()
    else:
        total_row = {column: None for column in DASHBOARD_TABLE_COLUMNS}
        total_row.update(
            _dashboard_aggregate_summary(pd, static_frame, campaigns)
        )
        total_row["funnel"] = "TOTALE GENERALE"
    total_row["_row_type"] = "total"
    output_rows.append(total_row)
    return pd.DataFrame(output_rows)


def build_campaign_table_html(display_df, row_types, excel_rows) -> str:
    """Render the campaign table with real rowspans for combined CRM pairs."""
    from src.combined_campaigns import COMBINED_CAMPAIGN_PAIRS

    merged_columns = {
        "Stima Lead",
        "Delta Lead",
        "CPL Effettivo",
        "Delta CPL",
    }
    pair_by_parent = dict(COMBINED_CAMPAIGN_PAIRS)
    row_type_values = list(row_types)
    excel_values = list(excel_rows)

    def excel_row(value) -> int | None:
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return None

    def column_class(column: str) -> str:
        if column == "Funnel":
            return "col-funnel"
        if column == "Canale":
            return "col-canale"
        if column == "Campagna":
            return "col-campagna"
        if column == "Action":
            return "col-action"
        slug = column.casefold().replace(" ", "-")
        return f"col-metric col-{slug}"

    skip_cells: set[tuple[int, str]] = set()
    rows_html: list[str] = []
    records = display_df.to_dict("records")
    for position, record in enumerate(records):
        current_row = excel_row(excel_values[position])
        child_row = pair_by_parent.get(current_row)
        pair_is_visible = (
            child_row is not None
            and position + 1 < len(records)
            and row_type_values[position] == "campaign"
            and row_type_values[position + 1] == "campaign"
            and excel_row(excel_values[position + 1]) == child_row
        )
        cells: list[str] = []
        for column in display_df.columns:
            if (position, column) in skip_cells:
                continue
            rowspan = ""
            if pair_is_visible and column in merged_columns:
                rowspan = ' rowspan="2"'
                skip_cells.add((position + 1, column))
            value = record.get(column)
            rendered = "" if value is None else str(value)
            cells.append(
                f'<td class="{column_class(column)}"{rowspan}>{rendered}</td>'
            )
        rows_html.append("<tr>" + "".join(cells) + "</tr>")

    headers = "".join(
        f'<th class="{column_class(column)}">{html.escape(column)}</th>'
        for column in display_df.columns
    )
    caption = (
        '<caption class="sr-only">Dettaglio delle campagne e dei principali '
        "indicatori di performance</caption>"
    )
    return (
        f'<table border="0" class="dataframe campaign-table">{caption}'
        f"<thead><tr>{headers}</tr></thead><tbody>{''.join(rows_html)}</tbody></table>"
    )


def build_csv_download(
    report_df, selected_start, selected_end
) -> tuple[bytes, str]:
    """Serialize the currently filtered report snapshot for the selected period."""
    export_df = report_df.copy()
    export_df["start_date"] = selected_start.isoformat()
    export_df["end_date"] = selected_end.isoformat()
    content = export_df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
    filename = f"report_data_{selected_start:%Y-%m-%d}_{selected_end:%Y-%m-%d}.csv"
    return content, filename


def calculate_dashboard_metrics(df, use_official_totals: bool = False) -> dict:
    """Calculate KPI values without altering campaign-level table data."""
    campaigns = (
        df
        if "row_type" not in df.columns
        else df[df["row_type"].fillna("campaign") == "campaign"]
    )
    source = campaigns
    legacy_official = use_official_totals and "row_type" not in df.columns
    if use_official_totals and "row_type" in df.columns:
        totals = df[df["row_type"] == "total"]
        if not totals.empty:
            source = totals.iloc[[0]]

    spend_available = source["speso_effettivo"].notna().any()
    spend_total = source["speso_effettivo"].sum(skipna=True) if spend_available else None
    budget_total = source["investimento_media"].sum(skipna=True)
    planned_spend = source["stima_spending_progressiva"].sum(skipna=True)
    lead_available = source["lead_effettive"].notna().any()
    lead_total = source["lead_effettive"].sum(skipna=True)
    lead_target = source["stima_lead_progressiva"].sum(skipna=True)
    cpl_target_avg = source["cpl_target"].mean(skipna=True)

    if legacy_official:
        def first_total(column: str):
            values = df[column].dropna() if column in df.columns else []
            return None if len(values) == 0 else float(values.iloc[0])

        spend_total = first_total("kpi_speso_effettivo_totale") or spend_total
        budget_total = first_total("kpi_investimento_media_totale") or budget_total
        planned_spend = first_total("kpi_stima_spending_progressiva_totale") or planned_spend
        lead_total = first_total("kpi_lead_effettive_totale") or lead_total
        lead_target = first_total("kpi_stima_lead_progressiva_totale") or lead_target
        cpl_target_avg = first_total("kpi_cpl_target_totale") or cpl_target_avg
        lead_available = lead_total is not None

    delta_spend = spend_total - planned_spend if spend_total is not None else None
    delivery_ratio = ratio(spend_total, planned_spend) if spend_total is not None else None
    lead_ratio = ratio(lead_total, lead_target) if lead_available else None
    cpl_avg = ratio(spend_total, lead_total) if lead_available and spend_total is not None else None
    if use_official_totals and len(source.index) == 1:
        row = source.iloc[0]
        if "delta_speso" in row and row.get("delta_speso") == row.get("delta_speso"):
            delta_spend = float(row["delta_speso"])
        if "delta_delivery_pct" in row and row.get("delta_delivery_pct") == row.get("delta_delivery_pct"):
            delivery_ratio = 1 + float(row["delta_delivery_pct"])
        if "cpl_effettivo" in row and row.get("cpl_effettivo") == row.get("cpl_effettivo"):
            cpl_avg = float(row["cpl_effettivo"])
    return {
        "spend_total": spend_total,
        "budget_total": budget_total,
        "planned_spend": planned_spend,
        "delta_spend": delta_spend,
        "delivery_ratio": delivery_ratio,
        "lead_available": lead_available,
        "lead_total": lead_total,
        "lead_target": lead_target,
        "lead_ratio": lead_ratio,
        "cpl_avg": cpl_avg,
        "cpl_target_avg": cpl_target_avg,
    }


def local_verification_enabled() -> bool:
    """Keep API verification opt-in and absent from the client deployment."""
    try:
        from dotenv import load_dotenv

        load_dotenv(Path(__file__).with_name(".env"), encoding="utf-8-sig")
    except ImportError:
        pass
    return os.getenv("LOCAL_VERIFICATION_MODE", "false").strip().lower() == "true"


def render_local_ads_verification(
    st, pd, metadata: dict, selected_start=None, selected_end=None
) -> None:
    """Render real read-only API checks only when explicitly enabled locally."""
    if not local_verification_enabled():
        return

    from src.ads_verification import verify_ads_connections
    from src.dates import current_month_until_yesterday

    fallback_start, fallback_end = current_month_until_yesterday()
    start_date = str(selected_start or metadata.get("start_date") or fallback_start.isoformat())
    end_date = str(selected_end or metadata.get("end_date") or fallback_end.isoformat())

    with st.expander("Verifica locale collegamenti Ads", expanded=False):
        st.caption(
            "Controllo locale in sola lettura. Questa sezione non è attiva nella versione cliente."
        )
        if st.button("Interroga Google Ads e Meta Ads", key="run_ads_verification"):
            with st.spinner("Lettura API in corso…"):
                st.session_state["ads_verification_rows"] = verify_ads_connections(
                    start_date, end_date
                )

        rows = st.session_state.get("ads_verification_rows")
        if not rows:
            st.info("Avvia la verifica per leggere i dati reali dello stesso periodo del report.")
            return

        verification_df = pd.DataFrame(rows).rename(
            columns={
                "platform": "Piattaforma",
                "campaign_id": "Campaign ID",
                "campaign_name": "Campaign name",
                "periodo_interrogato": "Periodo interrogato",
                "speso_estratto": "Speso estratto",
                "stato_collegamento": "Stato del collegamento",
                "errore": "Errore",
            }
        )
        st.dataframe(
            verification_df,
            width="stretch",
            hide_index=True,
            column_config={
                "Speso estratto": st.column_config.NumberColumn(format="€ %.2f"),
            },
        )


def main() -> None:
    try:
        import pandas as pd
        import streamlit as st
        import streamlit.components.v1 as components
    except ImportError:
        metadata = load_last_update()
        print(f"Dynamica Retail dashboard - status: {metadata.get('status')}")
        return

    st.set_page_config(page_title="Dynamica Retail", layout="wide")
    if "dark_mode" not in st.session_state:
        st.session_state.dark_mode = False
    apply_style(st)
    theme_name = "dark" if st.session_state.dark_mode else "light"
    st.markdown(f'<div id="dashboard-theme" data-theme="{theme_name}"></div>', unsafe_allow_html=True)

    metadata = load_last_update()
    report_df = prepare_data(pd)
    daily_spend = prepare_spend_daily(pd)
    daily_status = load_spend_daily_status()
    if "row_type" in report_df.columns:
        official_rows = report_df[report_df["row_type"].isin(["subtotal", "total"])].copy()
        campaign_df = report_df[report_df["row_type"] == "campaign"].copy()
    else:
        official_rows = report_df.iloc[0:0].copy()
        campaign_df = report_df.copy()
        campaign_df["row_type"] = "campaign"
    campaign_df = add_unmapped_daily_campaigns(pd, campaign_df, daily_spend)
    df = pd.concat([campaign_df, official_rows], ignore_index=True, sort=False)

    if df.empty:
        st.error("Dati dashboard non disponibili.")
        return

    filtered = render_sidebar(st, campaign_df)

    start_date = first_value(metadata, ["start_date"])
    end_date = first_value(metadata, ["end_date"])
    updated_at = first_value(metadata, ["updated_at"])
    status = first_value(metadata, ["status"])

    st.markdown(
        '<div class="font-preload" aria-hidden="true"><span>Work Sans</span><span>Work Sans</span><span>Work Sans</span><span>Work Sans</span></div>'
        f'<div class="header-actions"><div class="header-action">{svg_icon("power")}</div></div>'
        '<div class="page-title">Dashboard Dynamica Retail</div>',
        unsafe_allow_html=True,
    )
    if status == "partial":
        message = str(metadata.get("error") or "Una o più fonti non sono aggiornate.")
        st.warning(f"Aggiornamento parziale: {message}")
    elif status in {"error", "missing"}:
        st.error("L'ultimo aggiornamento non è stato completato. Sono mostrati gli ultimi dati disponibili.")

    top_left, top_right = st.columns([1, 1.08], gap="large")
    project_options = ["Tutti i progetti"] + sorted(
        str(value) for value in campaign_df["campaign_name"].dropna().unique()
    )
    yesterday = date.today() - timedelta(days=1)
    if daily_spend.empty:
        available_start = pd.to_datetime(start_date).date()
        available_end = min(pd.to_datetime(end_date).date(), yesterday)
    else:
        available_start = min(daily_spend["date"])
        available_end = min(max(daily_spend["date"]), yesterday)
    default_start = max(available_start, available_end.replace(day=1))
    st.session_state.setdefault("applied_start_date", default_start)
    st.session_state.setdefault("applied_end_date", available_end)
    with top_left:
        st.markdown(
            '<div class="filter-card-label project-filter-label">Progetto</div>',
            unsafe_allow_html=True,
        )
        selected_project = st.selectbox(
            "Progetto",
            project_options,
            label_visibility="collapsed",
            key="project_filter",
        )
    with top_right:
        st.markdown(
            '<div class="filter-card-label period-filter-label">Periodo</div>',
            unsafe_allow_html=True,
        )
        with st.form("period_filter_form", border=False):
            start_col, end_col, apply_col = st.columns([1, 1, .72], gap="small")
            with start_col:
                start_date = st.date_input(
                    "Data inizio",
                    value=st.session_state["applied_start_date"],
                    min_value=available_start,
                    max_value=available_end,
                    format="DD/MM/YYYY",
                    key="start_date",
                )
            with end_col:
                end_date = st.date_input(
                    "Data fine",
                    value=st.session_state["applied_end_date"],
                    min_value=available_start,
                    max_value=available_end,
                    format="DD/MM/YYYY",
                    key="end_date",
                )
            with apply_col:
                apply_period = st.form_submit_button(
                    "Applica periodo", width="stretch"
                )

    if selected_project != "Tutti i progetti":
        filtered = filtered[filtered["campaign_name"].astype(str) == selected_project]
    if apply_period:
        try:
            selected_start, selected_end = normalize_period(
                (start_date, end_date), default_start, available_end
            )
        except ValueError as exc:
            st.error(str(exc))
            return
        st.session_state["applied_start_date"] = selected_start
        st.session_state["applied_end_date"] = selected_end
    selected_start = st.session_state["applied_start_date"]
    selected_end = st.session_state["applied_end_date"]

    full_scope = (
        selected_project == "Tutti i progetti"
        and len(filtered.index) == len(campaign_df.index)
        and selected_start == pd.to_datetime(metadata["start_date"]).date()
        and selected_end == pd.to_datetime(metadata["end_date"]).date()
    )
    dynamic_all = apply_daily_spend_filter(
        pd, campaign_df, daily_spend, selected_start, selected_end
    )
    dynamic_filtered = dynamic_all.reindex(filtered.index)
    period_df = build_period_report_frame(
        pd, df, daily_spend, selected_start, selected_end
    )
    lead_metrics = calculate_dashboard_metrics(
        df if full_scope else dynamic_filtered, use_official_totals=full_scope
    )
    spend_metrics = calculate_dashboard_metrics(
        df if full_scope else dynamic_filtered, use_official_totals=full_scope
    )
    metrics = lead_metrics.copy()
    for key in ("spend_total", "planned_spend", "delta_spend", "delivery_ratio"):
        metrics[key] = spend_metrics[key]
    spend_total = metrics["spend_total"]
    budget_total = metrics["budget_total"]
    planned_spend = metrics["planned_spend"]
    delta_spend = metrics["delta_spend"]
    delivery_ratio = metrics["delivery_ratio"]
    lead_available = metrics["lead_available"]
    lead_total = metrics["lead_total"]
    lead_target = metrics["lead_target"]
    lead_ratio = metrics["lead_ratio"]
    cpl_avg = metrics["cpl_avg"]
    cpl_target_avg = metrics["cpl_target_avg"]
    short_end = selected_end.strftime("%d/%m")

    spend_vs_plan = delivery_ratio - 1 if delivery_ratio is not None else None
    spend_note = f"{percent(spend_vs_plan)} vs piano al {short_end}" if spend_vs_plan is not None else "— vs piano"
    spend_icon = "trend-up" if spend_vs_plan is None or spend_vs_plan >= 0 else "trend-down"

    if lead_ratio is None:
        lead_note = "— vs stima"
    elif abs(lead_ratio - 1) <= 0.05:
        lead_note = f"in linea con stima al {short_end}"
    else:
        lead_note = f"{percent(lead_ratio - 1)} vs stima al {short_end}"

    cpl_delta = cpl_avg - cpl_target_avg if cpl_avg is not None and not math.isnan(cpl_target_avg) else None
    if cpl_delta is None:
        cpl_note = "— vs CPL target"
    else:
        cpl_delta_text = money(abs(cpl_delta)).replace(" EUR", " €")
        cpl_note = f"{'+' if cpl_delta >= 0 else '-'}{cpl_delta_text} vs CPL target"

    delta_spend_color = (
        "#08a642"
        if delta_spend is not None and not pd.isna(delta_spend) and delta_spend < 0
        else "#ff9d00"
    )
    cpl_card_color = (
        "#08a642"
        if cpl_delta is not None and not pd.isna(cpl_delta) and cpl_delta < 0
        else "#ff9d00"
    )

    kpi_cols = st.columns([.93, .95, 1.0, 1.03], gap="medium")
    with kpi_cols[0]:
        render_kpi_card(
            st, "Speso totale", money(spend_total).replace(" EUR", " €"), spend_note,
            f"Budget mese: {money(budget_total).replace(' EUR', ' €')}", "#00a5b4", spend_icon, "check-circle"
        )
    with kpi_cols[1]:
        render_kpi_card(
            st, "Delta speso", money(delta_spend).replace(" EUR", " €"),
            "vs spending pianificato", "", delta_spend_color
        )
    with kpi_cols[2]:
        render_kpi_card(
            st, "Lead effettive", integer(lead_total) if lead_available else "—", lead_note,
            "", "#18c77a", "check-circle", None
        )
    with kpi_cols[3]:
        render_kpi_card(
            st, "CPL medio", money(cpl_avg).replace(" EUR", " €") if cpl_avg is not None else "—", cpl_note,
            f"CPL target medio: {money(cpl_target_avg).replace(' EUR', ' €')}", cpl_card_color, "trend-up", "target"
        )

    delivery_width = min(max(delivery_ratio or 0, 0), 1.2) / 1.2 * 100
    lead_width = min(max(lead_ratio or 0, 0), 1.2) / 1.2 * 100
    cpl_efficiency = None
    if cpl_avg is not None and cpl_target_avg and not math.isnan(cpl_target_avg):
        cpl_efficiency = (cpl_avg / cpl_target_avg) - 1

    lead_fraction = min(max(lead_ratio if lead_ratio is not None else 1, 0), 1)
    lead_progress = lead_fraction * 100
    lead_needle_angle = math.pi * (1 - lead_fraction)
    lead_needle_x = 110 + 82 * math.cos(lead_needle_angle)
    lead_needle_y = 105 - 82 * math.sin(lead_needle_angle)
    lead_base_x = 110 + 58 * math.cos(lead_needle_angle)
    lead_base_y = 105 - 58 * math.sin(lead_needle_angle)
    lead_perp_x = math.sin(lead_needle_angle) * 5
    lead_perp_y = math.cos(lead_needle_angle) * 5
    lead_base_1_x = lead_base_x + lead_perp_x
    lead_base_1_y = lead_base_y + lead_perp_y
    lead_base_2_x = lead_base_x - lead_perp_x
    lead_base_2_y = lead_base_y - lead_perp_y
    lead_progress_path = "<!-- progress unavailable -->"
    if lead_ratio is not None and lead_progress > 0:
        lead_progress_path = (
            f'<path class="gauge-progress" pathLength="100" stroke-dasharray="{lead_progress:.1f} 100" '
            'd="M20 105 A90 90 0 0 1 200 105"/>'
        )

    efficiency_for_needle = min(max(cpl_efficiency or 0, -0.2), 0.2)
    if efficiency_for_needle < -0.05:
        efficiency_fraction = ((efficiency_for_needle + 0.2) / 0.15) / 3
    elif efficiency_for_needle <= 0.05:
        efficiency_fraction = 1 / 3 + ((efficiency_for_needle + 0.05) / 0.10) / 3
    else:
        efficiency_fraction = 2 / 3 + ((efficiency_for_needle - 0.05) / 0.15) / 3
    efficiency_angle = math.radians(180 - efficiency_fraction * 180)
    efficiency_needle_x = 110 + 58 * math.cos(efficiency_angle)
    efficiency_needle_y = 105 - 58 * math.sin(efficiency_angle)
    efficiency_perp_x = math.sin(efficiency_angle) * 4
    efficiency_perp_y = math.cos(efficiency_angle) * 4
    efficiency_base_1_x = 110 + efficiency_perp_x
    efficiency_base_1_y = 105 + efficiency_perp_y
    efficiency_base_2_x = 110 - efficiency_perp_x
    efficiency_base_2_y = 105 - efficiency_perp_y
    if cpl_efficiency is None:
        efficiency_color = "#ff8a00"
    elif cpl_efficiency < -0.05:
        efficiency_color = "#f20d18"
    elif cpl_efficiency <= 0.05:
        efficiency_color = "#ff8a00"
    else:
        efficiency_color = "#08a642"

    middle = st.columns([.92, 1.55, 1.31], gap="medium")
    with middle[0]:
        st.markdown(
            f"""
            <div class="panel">
              <div class="panel-title">Delivery Lead</div>
              <div class="svg-gauge">
                <svg viewBox="0 0 220 125" aria-hidden="true">
                  <path class="gauge-track" pathLength="100" d="M20 105 A90 90 0 0 1 200 105"/>
                  {lead_progress_path}
                  <path class="gauge-needle-shape" d="M{lead_base_1_x:.1f} {lead_base_1_y:.1f} L{lead_base_2_x:.1f} {lead_base_2_y:.1f} L{lead_needle_x:.1f} {lead_needle_y:.1f} Z"/>
                </svg>
                <div class="svg-gauge-value">{percent(lead_ratio) if lead_ratio is not None else '—'}</div>
                <div class="svg-gauge-caption">vs stima lead</div>
                <div class="svg-gauge-target">Target: 100,0%</div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with middle[1]:
        st.markdown(
            f"""
            <div class="panel progress-panel">
              <div class="panel-title">Stato avanzamento campagne</div>
              <div class="target-marker">TARGET</div>
              <div class="progress-row">
                <div class="progress-label"><span>Spending effettivo</span><span></span></div>
                <div class="bar"><div class="bar-fill" style="--width:{delivery_width:.1f}%">{percent(delivery_ratio)}</div></div>
              </div>
              <div class="progress-row">
                <div class="progress-label"><span>Lead effettive</span><span></span></div>
                <div class="bar"><div class="bar-fill" style="--width:{lead_width:.1f}%">{percent(lead_ratio)}</div></div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with middle[2]:
        st.markdown(
            f"""
            <div class="panel">
              <div class="panel-title">Indice efficienza CPL</div>
              <div class="cpl-gauge" style="--eff-color:{efficiency_color}">
                <svg viewBox="0 0 220 125" aria-hidden="true">
                  <path class="cpl-arc" stroke="#f20d18" d="M20 105 A90 90 0 0 1 65 27.1"/>
                  <path class="cpl-arc" stroke="#ff9d00" d="M65 27.1 A90 90 0 0 1 155 27.1"/>
                  <path class="cpl-arc" stroke="#08a642" d="M155 27.1 A90 90 0 0 1 200 105"/>
                  <g transform="translate(0 -18)">
                    <path class="gauge-needle-shape" d="M{efficiency_base_1_x:.1f} {efficiency_base_1_y:.1f} L{efficiency_base_2_x:.1f} {efficiency_base_2_y:.1f} L{efficiency_needle_x:.1f} {efficiency_needle_y:.1f} Z"/>
                    <circle class="gauge-pin cpl-pin" cx="110" cy="105" r="7"/>
                  </g>
                </svg>
                <div class="cpl-gauge-value">{percent(cpl_efficiency) if cpl_efficiency is not None else '—'}</div>
                <div class="eff-note"><span class="legend-dot" style="background:#f20d18"></span>rosso = meglio del target <span class="legend-dot" style="background:#ff9d00"></span>giallo = in linea <span class="legend-dot" style="background:#08a642"></span>verde = sopra target</div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    table_frame = build_dashboard_table_frame(
        pd,
        filtered,
        period_df[period_df["row_type"] == "campaign"] if full_scope else dynamic_filtered,
        period_df,
        full_scope=full_scope,
    )
    table_excel_rows = (
        table_frame["excel_row"].copy()
        if "excel_row" in table_frame
        else pd.Series([None] * len(table_frame), index=table_frame.index)
    )
    row_types = table_frame.pop("_row_type")
    display_df = table_frame[
        [column for column in DASHBOARD_TABLE_COLUMNS if column in table_frame.columns]
    ].rename(columns=DASHBOARD_TABLE_COLUMNS)

    for column in ["Stima Lead", "Lead Effettive"]:
        if column in display_df:
            display_df[column] = display_df[column].map(integer)
    for column in [
        "Stima Spending",
        "Speso Effettivo",
        "CPL Target",
        "CPL Effettivo",
    ]:
        if column in display_df:
            display_df[column] = display_df[column].map(money)

    def format_delta(value, *, negative_is_good: bool, formatter) -> str:
        if pd.isna(value):
            return '<span class="delta-value delta-neutral">—</span>'
        numeric_value = float(value)
        if numeric_value == 0:
            css_class = "delta-neutral"
        elif (numeric_value < 0) == negative_is_good:
            css_class = "delta-good"
        else:
            css_class = "delta-bad"
        formatted = formatter(numeric_value)
        if numeric_value > 0:
            formatted = f"+{formatted}"
        return f'<span class="delta-value {css_class}">{formatted}</span>'

    if "Delta Lead" in display_df:
        display_df["Delta Lead"] = display_df["Delta Lead"].map(
            lambda value: format_delta(value, negative_is_good=False, formatter=integer)
        )
    for column in ["Delta Speso", "Delta CPL"]:
        if column in display_df:
            display_df[column] = display_df[column].map(
                lambda value: format_delta(value, negative_is_good=True, formatter=money)
            )

    if "Action" in display_df:
        action_icon = svg_icon("message")

        def format_action(value) -> str:
            if pd.isna(value) or not str(value).strip():
                return '<span class="delta-neutral">—</span>'
            action = html.escape(str(value).strip())
            return f'<div class="action-cell" title="{action}">{action_icon}<span class="action-text">{action}</span></div>'

        display_df["Action"] = [
            format_action(value) if row_types.iloc[index] == "campaign" else ""
            for index, value in enumerate(display_df["Action"])
        ]

    if "Canale" in display_df:
        display_df["Canale"] = display_df["Canale"].fillna("").map(
            lambda value: html.escape(str(value))
        )

    if "Campagna" in display_df:
        display_df["Campagna"] = display_df["Campagna"].fillna("")
        for position, index in enumerate(display_df.index):
            campaign = html.escape(str(display_df.at[index, "Campagna"] or ""))
            if row_types.iloc[position] == "campaign" and campaign:
                display_df.at[index, "Campagna"] = (
                    f'<span class="campaign-name" title="{campaign}">{campaign}</span>'
                )
            else:
                display_df.at[index, "Campagna"] = campaign

    if "Funnel" in display_df:
        for position, index in enumerate(display_df.index):
            row_type = row_types.iloc[position]
            label = html.escape(str(display_df.at[index, "Funnel"] or ""))
            if row_type not in {"subtotal", "total"}:
                display_df.at[index, "Funnel"] = label
                continue
            marker = (
                "subtotal-row-marker" if row_type == "subtotal" else "total-row-marker"
            )
            display_df.at[index, "Funnel"] = (
                f'<span class="{marker}" aria-hidden="true"></span>{label}'
            )

    table_header, download_col = st.columns([1, .215])
    with table_header:
        st.markdown('<div class="table-title"></div>', unsafe_allow_html=True)
    with download_col:
        try:
            excel_bytes, excel_filename = build_excel_download(
                pd,
                df,
                daily_spend,
                metadata,
                selected_start,
                selected_end,
            )
            st.download_button(
                "Scarica il report completo",
                excel_bytes,
                file_name=excel_filename,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                width="stretch",
            )
            csv_bytes, csv_filename = build_csv_download(
                period_df, selected_start, selected_end
            )
            st.download_button(
                "Scarica CSV dati",
                csv_bytes,
                file_name=csv_filename,
                mime="text/csv",
                width="stretch",
                key="download_csv_data",
            )
        except Exception:
            st.error("I file di esportazione non sono momentaneamente disponibili.")

    table_html = build_campaign_table_html(
        display_df,
        row_types,
        table_excel_rows,
    )
    st.markdown(
        f'<div class="campaign-table-wrap" role="region" tabindex="0" aria-label="Tabella campagne, scorrimento orizzontale">{table_html}</div>',
        unsafe_allow_html=True,
    )

    render_local_ads_verification(st, pd, metadata, selected_start, selected_end)
    render_project_tooltips(components, selected_project)


if __name__ == "__main__":
    main()
