"""Configuration helpers for the Dynamica Retail flow."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    """Runtime settings loaded from environment variables."""

    client_name: str = "Dynamica Retail"
    timezone: str = "Europe/Rome"
    dynamics_enabled: bool = False


def load_settings() -> Settings:
    """Load basic settings without reading secrets or calling external services."""
    return Settings(
        client_name=os.getenv("CLIENT_NAME", "Dynamica Retail"),
        timezone=os.getenv("TIMEZONE", "Europe/Rome"),
        dynamics_enabled=os.getenv("DYNAMICS_ENABLED", "false").lower() == "true",
    )
