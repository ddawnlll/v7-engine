"""AlphaForge report writer.

Writes report payloads as JSON to caller-provided paths.
Optionally validates before writing.
"""
import json
from pathlib import Path

from alphaforge.contracts.validator import validate_payload
from alphaforge.errors import ContractValidationError


def write_json_report(
    payload: dict,
    output_path: str | Path,
    schema: dict | None = None,
    schema_name: str = "unknown",
) -> Path:
    """Write a report payload as JSON.

    Args:
        payload: Report dict to serialize.
        output_path: Destination path (file will be created or overwritten).
        schema: Optional JSON schema dict. If provided, validates before writing.
        schema_name: Label for validation error messages.

    Returns:
        Path to the written file.

    Raises:
        ContractValidationError: If schema validation fails.
        OSError: If file cannot be written.
    """
    output = Path(output_path)

    # Validate before write if schema provided
    if schema is not None:
        result = validate_payload(schema, payload, schema_name)
        if not result.valid:
            raise ContractValidationError(
                f"Report failed validation before write ({schema_name}): {result.errors}"
            )

    # Create parent directories
    output.parent.mkdir(parents=True, exist_ok=True)

    with open(output, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    return output
