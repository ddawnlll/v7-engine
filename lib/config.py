"""Centralised environment configuration for V7 Engine.

Loads all configuration from environment variables with sensible defaults.
This module is the single source of truth for env-var names, fallbacks, and
validation.  Importing it does NOT fail on missing secrets — call
``validate_required_secrets()`` explicitly at startup for that.

Usage::

    from lib.config import config, validate_required_secrets

    # Access configuration values with defaults
    log_level = config.runtime_log_level
    db_url = config.database_url

    # Validate required secrets at process start
    validate_required_secrets()
"""

from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass, field

__all__ = ["Config", "config", "validate_required_secrets"]

logger = logging.getLogger(__name__)


def _bool_env(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on", "enable", "enabled"}


def _resolve_database_url() -> str | None:
    return (
        os.environ.get("V4_DATABASE_URL")
        or os.environ.get("V4_POSTGRES_URL")
        or os.environ.get("V3_POSTGRES_URL")
        or os.environ.get("DATABASE_URL")
    )


@dataclass(frozen=True)
class Config:
    # ── Environment ───────────────────────────────────────────────
    environment: str = field(
        default_factory=lambda: os.environ.get("ENVIRONMENT", "development")
    )

    # ── API Server ────────────────────────────────────────────────
    api_host: str = field(
        default_factory=lambda: os.environ.get("API_HOST", "0.0.0.0")
    )
    api_port: int = field(
        default_factory=lambda: int(os.environ.get("API_PORT", "8000"))
    )

    # ── Database ──────────────────────────────────────────────────
    database_url: str | None = field(default_factory=_resolve_database_url)

    # ── Logging ───────────────────────────────────────────────────
    runtime_log_level: str = field(
        default_factory=lambda: os.environ.get("RUNTIME_LOG_LEVEL", "INFO")
    )
    log_format: str = field(
        default_factory=lambda: os.environ.get(
            "LOG_FORMAT", "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        )
    )
    log_dir: str = field(
        default_factory=lambda: os.environ.get("LOG_DIR", "./logs")
    )

    # ── Exchange Credentials (Binance) ────────────────────────────
    binance_api_key: str | None = field(
        default_factory=lambda: os.environ.get("BINANCE_API_KEY")
    )
    binance_secret: str | None = field(
        default_factory=lambda: os.environ.get("BINANCE_SECRET")
    )
    # Dynamic credential-ref-based exchange keys are resolved at runtime
    # by RuntimeProfileService._resolve_credentials(), not here.

    # ── AI / LLM Services ─────────────────────────────────────────
    anthropic_api_key: str | None = field(
        default_factory=lambda: os.environ.get("ANTHROPIC_API_KEY")
    )
    anthropic_model: str = field(
        default_factory=lambda: os.environ.get(
            "ANTHROPIC_MODEL", "claude-sonnet-4-20250514"
        )
    )

    # ── Paper Trading ─────────────────────────────────────────────
    paper_starting_cash: float = field(
        default_factory=lambda: float(
            os.environ.get("V4_PAPER_STARTING_CASH", "100.0")
        )
    )

    # ── HTTP / Proxy ──────────────────────────────────────────────
    http_trust_env: bool = field(
        default_factory=lambda: _bool_env("RUNTIME_HTTP_TRUST_ENV", default=False)
    )

    # ── Data Paths ────────────────────────────────────────────────
    data_dir: str = field(
        default_factory=lambda: os.environ.get("DATA_DIR", "./data")
    )

    # ── Derived ───────────────────────────────────────────────────
    @property
    def is_development(self) -> bool:
        return self.environment == "development"

    @property
    def is_staging(self) -> bool:
        return self.environment == "staging"

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def is_live(self) -> bool:
        return self.environment in ("staging", "production")


# Singleton instance.
config = Config()


def validate_required_secrets() -> None:
    """Validate that required secrets are present.  Call at startup.

    Prints clear error messages and exits with code 1 if any required
    secret is missing.  The check is deliberately strict in production
    and advisory-only in development.
    """
    missing: list[str] = []

    if not config.database_url and config.is_production:
        missing.append(
            "DATABASE_URL (or V4_DATABASE_URL / V4_POSTGRES_URL / V3_POSTGRES_URL)"
        )

    # Binance credentials are not globally required — they are per-profile.
    # But if the legacy BINANCE_API_KEY is set without BINANCE_SECRET or vice
    # versa, warn.
    legacy_key = config.binance_api_key
    legacy_secret = config.binance_secret

    if (legacy_key and not legacy_secret) or (legacy_secret and not legacy_key):
        logger.warning(
            "BINANCE_API_KEY and BINANCE_SECRET should both be set or both empty. "
            "One is missing — exchanges using the legacy env vars will fail."
        )
        if config.is_production:
            missing.append("BINANCE_API_KEY + BINANCE_SECRET (both required when either is set)")

    if config.is_production and not config.anthropic_api_key:
        logger.warning(
            "ANTHROPIC_API_KEY is not set. The failure classifier will fall back to "
            "heuristic-only classification (no LLM analysis of trade failures)."
        )

    if missing:
        print("\n=== SECRETS VALIDATION FAILED ===\n", file=sys.stderr)
        for item in missing:
            print(f"  MISSING: {item}", file=sys.stderr)
        print(
            "\nCopy .env.example to .env and fill in the required values.\n",
            file=sys.stderr,
        )
        sys.exit(1)

    if not config.database_url:
        logger.info("No DATABASE_URL set — using sqlite:// (in-memory) by default.")

    logger.info(
        "Secrets validation passed. environment=%s database=%s anthropic=%s",
        config.environment,
        "configured" if config.database_url else "sqlite:// (default)",
        "configured" if config.anthropic_api_key else "not configured",
    )
