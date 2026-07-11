"""Authoritative SimulationProfile registry.

Provides deterministic lookup of canonical simulation profiles by mode
and profile version. Every profile has a unique identity:

    profile_hash = sha256(canonical YAML representation of all fields)

The registry is the single source of truth for production profiles.
Unknown modes or versions fail fast with ValueError.
"""
