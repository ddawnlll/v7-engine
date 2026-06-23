"""AlphaForge errors — explicit domain exceptions.

All AlphaForge errors inherit from AlphaForgeError so callers can
catch domain errors without leaking implementation details.

Error messages are structured and suitable for ACCP-YAML reports.
"""

from typing import Optional, List


class AlphaForgeError(Exception):
    """Base exception for all AlphaForge domain errors."""
    pass


class ContractError(AlphaForgeError):
    """Schema or fixture load/validation failure."""
    pass


class ContractLoadError(ContractError):
    """File not found or invalid JSON."""
    pass


class ContractValidationError(ContractError):
    """Payload failed schema validation."""
    pass


class ModeError(AlphaForgeError):
    """Invalid or unknown mode."""
    pass


class ReportBuildError(AlphaForgeError):
    """Report builder could not produce valid payload."""
    pass


class HandoffBuildError(AlphaForgeError):
    """Handoff builder could not produce valid payload."""
    pass


class RegistryError(AlphaForgeError):
    """Contract registry or compatibility mapping error."""

    def __init__(self, detail: str):
        self.detail = detail
        super().__init__(f"Registry error: {detail}")


class SchemaLoadError(AlphaForgeError):
    """Failed to load a JSON schema file."""

    def __init__(self, schema_path: str, reason: str):
        self.schema_path = schema_path
        self.reason = reason
        super().__init__(f"Schema load failed for {schema_path}: {reason}")


class ValidationError(AlphaForgeError):
    """Fixture or report failed schema validation."""

    def __init__(
        self,
        schema_name: str,
        fixture_path: str,
        errors: List[str],
        missing_required: Optional[List[str]] = None,
    ):
        self.schema_name = schema_name
        self.fixture_path = fixture_path
        self.errors = errors
        self.missing_required = missing_required or []
        msg = f"Validation failed for {schema_name} ({fixture_path}): {'; '.join(errors)}"
        if self.missing_required:
            msg += f" | Missing required: {self.missing_required}"
        super().__init__(msg)


class MHTBlockingError(ValidationError):
    """MHT/data-snooping controls are missing or insufficient."""

    def __init__(self, schema_name: str, fixture_path: str, mht_status: str):
        self.mht_status = mht_status
        super().__init__(
            schema_name=schema_name,
            fixture_path=fixture_path,
            errors=[
                f"MHT status is {mht_status} — strong edge/profitability claims are blocked."
            ],
        )


class GateMappingError(AlphaForgeError):
    """V7 gate mapping contains invalid or old gate names."""

    def __init__(self, invalid_gates: List[str], allowed_gates: List[str]):
        self.invalid_gates = invalid_gates
        self.allowed_gates = allowed_gates
        super().__init__(
            f"Invalid gate names: {invalid_gates}. Allowed: {allowed_gates}"
        )


class HandoffBlockedError(AlphaForgeError):
    """Handoff package cannot be emitted — blocked by evidence gaps."""

    def __init__(self, block_reasons: List[str]):
        self.block_reasons = block_reasons
        super().__init__(f"Handoff blocked: {'; '.join(block_reasons)}")


class ConfigError(AlphaForgeError):
    """Configuration error — missing or invalid config."""

    def __init__(self, key: str, detail: str):
        self.key = key
        self.detail = detail
        super().__init__(f"Config error [{key}]: {detail}")
