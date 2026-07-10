"""Outcome cache: persist, index, and query candidate trade outcomes."""

from .schema import OutcomeRecord, OUTCOME_CACHE_SCHEMA_V1, METADATA_SCHEMA
from .writer import OutcomeCacheWriter
from .reader import OutcomeCacheReader

__all__ = [
    "OutcomeRecord",
    "OutcomeCacheWriter",
    "OutcomeCacheReader",
    "OUTCOME_CACHE_SCHEMA_V1",
    "METADATA_SCHEMA",
]
