"""Secrets and credential management for the V7 runtime.

Provides credential validation, resolution, and masking utilities.
Credentials are sourced from environment variables, with support for
per-profile resolution.
"""

from __future__ import annotations

import os
from typing import Any


# Canonical credential definitions: name -> (env_var_name, description)
REQUIRED_CREDENTIALS: dict[str, tuple[str, str]] = {
    "binance_api_key": ("BINANCE_API_KEY", "Binance API key"),
    "binance_secret": ("BINANCE_SECRET", "Binance API secret"),
    "binance_usdm_main_api_key": (
        "BINANCE_USDM_MAIN_API_KEY",
        "Binance USDM Main profile API key",
    ),
    "binance_usdm_main_api_secret": (
        "BINANCE_USDM_MAIN_API_SECRET",
        "Binance USDM Main profile API secret",
    ),
    "anthropic_api_key": ("ANTHROPIC_API_KEY", "Anthropic Claude API key"),
    "database_url": ("DATABASE_URL", "PostgreSQL connection URL"),
}


def get_credential(name: str) -> str | None:
    """Get a credential value from environment variables.

    Args:
        name: The credential name (key in REQUIRED_CREDENTIALS).

    Returns:
        The credential value, or None if not set.
    """
    entry = REQUIRED_CREDENTIALS.get(name)
    if entry is None:
        return None
    return os.environ.get(entry[0]) or None


def mask_secret(value: str | None, visible_chars: int = 4) -> str:
    """Mask a secret for display in logs.

    Shows the last ``visible_chars`` characters, masks the rest.
    Returns ``'<not set>'`` if *value* is None or empty.
    """
    if not value:
        return "<not set>"
    if len(value) <= visible_chars:
        return "*" * (len(value) - 1) + value[-1]
    return "*" * (len(value) - visible_chars) + value[-visible_chars:]


def validate_credentials() -> dict[str, list[str]]:
    """Check which required credentials are set.

    Returns:
        Dict with ``'present'`` and ``'missing'`` lists of credential names.
    """
    present: list[str] = []
    missing: list[str] = []

    for name, (env_var, _description) in REQUIRED_CREDENTIALS.items():
        value = os.environ.get(env_var)
        if value and value.strip():
            present.append(name)
        else:
            missing.append(name)

    return {"present": sorted(present), "missing": sorted(missing)}


def get_credential_report() -> dict[str, Any]:
    """Full credential status report for health endpoints.

    Returns:
        Dict keyed by credential name with status, masked value, description.
    """
    report: dict[str, Any] = {}
    for name, (env_var, description) in REQUIRED_CREDENTIALS.items():
        value = os.environ.get(env_var)
        report[name] = {
            "set": bool(value and value.strip()),
            "masked_value": mask_secret(value),
            "description": description,
            "env_var": env_var,
        }
    return report
