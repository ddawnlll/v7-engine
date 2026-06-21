"""AlphaForge errors — explicit domain exceptions.

All AlphaForge errors inherit from AlphaForgeError so callers can
catch domain errors without leaking implementation details.
"""


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
    """Contract registry error."""
    pass
