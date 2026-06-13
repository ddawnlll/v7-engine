"""
Lightweight structured logging helpers.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone


def log_event(event: str, **fields):
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": event,
        "pid": os.getpid(),
    }
    payload.update(fields)
    sys.stdout.write(json.dumps(payload, ensure_ascii=True) + "\n")
    sys.stdout.flush()
