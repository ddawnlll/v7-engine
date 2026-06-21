"""AlphaForge schema validation.

Validates payloads against JSON schemas. Falls back to basic
required-field and type checking when jsonschema is not installed.
"""
from typing import Any

from alphaforge.errors import ContractValidationError
from alphaforge.contracts.loader import load_schema, load_all_fixtures_for_schema, SCHEMA_FIXTURE_MAP


class ValidationResult:
    """Structured validation result."""
    def __init__(self, valid: bool, errors: list[str], warnings: list[str] | None = None):
        self.valid = valid
        self.errors = errors
        self.warnings = warnings or []

    def __bool__(self) -> bool:
        return self.valid

    def __repr__(self) -> str:
        status = "VALID" if self.valid else f"INVALID ({len(self.errors)} errors)"
        return f"ValidationResult({status})"


def _validate_required(instance: dict, schema: dict, path: str = "$") -> list[str]:
    """Check top-level required fields."""
    errors = []
    required = schema.get("required", [])
    for field in required:
        if field not in instance:
            errors.append(f"{path}: missing required field '{field}'")
    return errors


def _validate_type(instance: Any, schema: dict, path: str = "$") -> list[str]:
    """Check type of instance against schema type."""
    errors = []
    expected_type = schema.get("type")
    if expected_type is None:
        return errors

    type_map = {
        "string": str,
        "number": (int, float),
        "integer": int,  # JSON Schema 'integer' — allow Python int only in strict mode
        "boolean": bool,
        "object": dict,
        "array": list,
    }

    if expected_type == "integer":
        # In JSON Schema, integer means no decimal. Python int is fine.
        if isinstance(instance, bool) or not isinstance(instance, int):
            errors.append(f"{path}: expected integer, got {type(instance).__name__}")
    elif expected_type == "number":
        if isinstance(instance, bool) or not isinstance(instance, (int, float)):
            errors.append(f"{path}: expected number, got {type(instance).__name__}")
    elif expected_type in type_map:
        expected_py = type_map[expected_type]
        if not isinstance(instance, expected_py):
            errors.append(f"{path}: expected {expected_type}, got {type(instance).__name__}")

    return errors


def _validate_nested_required(instance: dict, schema: dict, path: str = "$") -> list[str]:
    """Recursively check nested required within object properties."""
    errors = []
    properties = schema.get("properties", {})
    for prop_name, prop_schema in properties.items():
        if prop_schema.get("type") != "object":
            continue
        nested_required = prop_schema.get("required", [])
        if not nested_required:
            continue
        prop_value = instance.get(prop_name)
        if prop_value is None:
            continue
        if not isinstance(prop_value, dict):
            errors.append(f"{path}.{prop_name}: expected object, got {type(prop_value).__name__}")
            continue
        for nr in nested_required:
            if nr not in prop_value:
                errors.append(f"{path}.{prop_name}: missing nested required field '{nr}'")
    return errors


def _validate_enum(instance: dict, schema: dict, path: str = "$") -> list[str]:
    """Check enum constraints on top-level and nested properties."""
    errors = []
    properties = schema.get("properties", {})
    for prop_name, prop_schema in properties.items():
        enum_values = prop_schema.get("enum")
        if enum_values is None:
            continue
        value = instance.get(prop_name)
        if value is not None and value not in enum_values:
            errors.append(
                f"{path}.{prop_name}: '{value}' not in allowed values {enum_values}"
            )
    return errors


def validate_payload(schema: dict, instance: dict, schema_name: str = "unknown") -> ValidationResult:
    """Validate an instance dict against a JSON schema dict.

    Uses jsonschema if available; falls back to basic constraint checks.

    Args:
        schema: JSON Schema as dict.
        instance: Payload to validate.
        schema_name: Name for error messages.

    Returns:
        ValidationResult with valid flag and error list.
    """
    errors: list[str] = []
    warnings: list[str] = []

    # Try jsonschema first for comprehensive validation
    try:
        import jsonschema as js
        js.validate(instance=instance, schema=schema)
        return ValidationResult(True, [], [])
    except ImportError:
        warnings.append("jsonschema not installed — using basic validation only")
    except Exception as e:
        # jsonschema found an error — report it
        errors.append(f"jsonschema validation error: {e}")
        return ValidationResult(False, errors, warnings)

    # Fallback: basic constraint checks
    errors.extend(_validate_type(instance, schema, schema_name))
    errors.extend(_validate_required(instance, schema, schema_name))
    errors.extend(_validate_enum(instance, schema, schema_name))
    errors.extend(_validate_nested_required(instance, schema, schema_name))

    return ValidationResult(len(errors) == 0, errors, warnings)


def validate_fixture(schema_name: str, fixture_name: str) -> ValidationResult:
    """Load and validate a specific fixture against its schema.

    Args:
        schema_name: e.g. 'mode_research_report.schema.json'
        fixture_name: e.g. 'scalp_mode_research_report_minimal.json'

    Returns:
        ValidationResult.
    """
    schema = load_schema(schema_name)
    from alphaforge.contracts.loader import load_fixture
    instance = load_fixture(fixture_name)
    return validate_payload(schema, instance, fixture_name)


def validate_all_known_fixtures() -> dict[str, list[ValidationResult]]:
    """Validate all known fixtures against their schemas.

    Returns:
        Dict mapping schema_name → list of ValidationResults for each fixture.
        Empty list for schemas with no mapped fixtures.
    """
    results: dict[str, list[ValidationResult]] = {}
    for schema_name, fixture_names in SCHEMA_FIXTURE_MAP.items():
        schema_results = []
        for fixture_name in fixture_names:
            schema_results.append(validate_fixture(schema_name, fixture_name))
        results[schema_name] = schema_results
    return results


def is_fixture_valid(schema_name: str, fixture_name: str) -> bool:
    """Check if a specific fixture validates. Returns True/False."""
    result = validate_fixture(schema_name, fixture_name)
    return result.valid
