"""Configuration helpers for the Dynamica Retail flow."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Settings:
    """Runtime settings loaded from environment variables."""

    client_name: str = "Dynamica Retail"
    timezone: str = "Europe/Rome"
    dynamics_enabled: bool = False
    local_verification_mode: bool = False


def load_settings() -> Settings:
    """Load basic settings without calling external services."""
    load_dotenv(ROOT / ".env", encoding="utf-8-sig")
    return Settings(
        client_name=os.getenv("CLIENT_NAME", "Dynamica Retail"),
        timezone=os.getenv("TIMEZONE", "Europe/Rome"),
        dynamics_enabled=os.getenv("DYNAMICS_ENABLED", "false").lower() == "true",
        local_verification_mode=os.getenv(
            "LOCAL_VERIFICATION_MODE", "false"
        ).lower() == "true",
    )
