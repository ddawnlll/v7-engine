"""Validate fixtures/reports against schemas.

Uses jsonschema if available; falls back to structural validator.
MHT blocking semantics enforced regardless of validation backend.
"""

from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional

from .contracts import load_json
from .errors import ValidationError, MHTBlockingError


def _has_jsonschema() -> bool:
    try:
        import jsonschema  # noqa: F401
        return True
    except ImportError:
        return False


def _validate_with_jsonschema(
    instance: Dict[str, Any], schema: Dict[str, Any]
) -> List[str]:
    try:
        import jsonschema as _js
        validator = _js.Draft7Validator(schema)
        return [e.message for e in validator.iter_errors(instance)]
    except ImportError:
        return ["jsonschema not available"]


def _validate_structural(
    instance: Dict[str, Any], schema: Dict[str, Any]
) -> List[str]:
    """Minimal structural validation — fallback when jsonschema unavailable."""
    errors: List[str] = []
    required = schema.get("required", [])
    for field in required:
        if field not in instance:
            errors.append(f"Missing required field: '{field}'")
    properties = schema.get("properties", {})
    for field, value in instance.items():
        if field in properties:
            prop = properties[field]
            expected = prop.get("type")
            if expected and not _type_matches(value, expected):
                errors.append(
                    f"Field '{field}': expected {expected}, got {type(value).__name__}"
                )
    return errors


def _type_matches(value: Any, expected_type: str) -> bool:
    type_map = {
        "string": str, "number": (int, float), "integer": int,
        "boolean": bool, "array": list, "object": dict,
    }
    expected = type_map.get(expected_type)
    if expected is None:
        return True
    if isinstance(expected, tuple):
        return isinstance(value, expected)
    return isinstance(value, expected)


def _find_missing(instance: Dict[str, Any], schema: Dict[str, Any]) -> List[str]:
    required = schema.get("required", [])
    return [f for f in required if f not in instance]


def _check_mht(
    schema_name: str,
    fixture_path: str,
    instance: Dict[str, Any],
    schema: Dict[str, Any],
) -> None:
    """Raise MHTBlockingError if MHT status blocks claims."""
    mht = instance.get("multiple_hypothesis_control")
    if mht is None:
        if "multiple_hypothesis_control" in schema.get("required", []):
            raise MHTBlockingError(schema_name, fixture_path, "MISSING")
        return
    status = mht.get("mht_status") or mht.get("aggregate_mht_status")
    if status in ("NOT_RUN", "NONE_APPLIED"):
        raise MHTBlockingError(schema_name, fixture_path, status)


def validate_fixture(
    schema_name: str,
    fixture_path: Path,
    schema: Optional[Dict[str, Any]] = None,
) -> Tuple[bool, List[str]]:
    """Validate a fixture file against its named schema.

    Returns (is_valid, error_messages). Raises ValidationError on failure.
    """
    if schema is None:
        from .schema_loader import load_schema
        schema = load_schema(schema_name)

    instance = load_json(fixture_path)

    if _has_jsonschema():
        errors = _validate_with_jsonschema(instance, schema)
    else:
        errors = _validate_structural(instance, schema)

    if errors:
        missing = _find_missing(instance, schema)
        raise ValidationError(
            schema_name=schema_name,
            fixture_path=str(fixture_path),
            errors=errors,
            missing_required=missing,
        )

    _check_mht(schema_name, str(fixture_path), instance, schema)
    return True, []


def validate_report(
    schema_name: str,
    report_path: Path,
    schema: Optional[Dict[str, Any]] = None,
) -> Tuple[bool, List[str]]:
    """Validate a report — same as validate_fixture with MHT check."""
    return validate_fixture(schema_name, report_path, schema)


def validate_empty_payload_fails(
    schema_name: str,
    schema: Optional[Dict[str, Any]] = None,
) -> bool:
    """Verify empty object {} fails validation. Returns True if strict enough."""
    if schema is None:
        from .schema_loader import load_schema
        schema = load_schema(schema_name)
    instance: Dict[str, Any] = {}
    if _has_jsonschema():
        errors = _validate_with_jsonschema(instance, schema)
    else:
        errors = _validate_structural(instance, schema)
    return len(errors) > 0
