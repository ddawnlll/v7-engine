"""Shared fixtures for runtime tests."""

import os

# Use in-memory SQLite to avoid needing a real database
os.environ.setdefault("V4_DATABASE_URL", "sqlite://")
