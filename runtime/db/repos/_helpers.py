from __future__ import annotations

import json
from typing import Any


def dumps_json(value: Any) -> str:
    return json.dumps(value if value is not None else {})


def dumps_list(value: Any) -> str:
    return json.dumps(value if value is not None else [])


def loads_json(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except Exception:
        return fallback
