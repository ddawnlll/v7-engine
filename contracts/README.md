# contracts/ — Root-Level Passive Contract Authority

## Purpose

This directory is the **canonical root contract registry** for the V7 Engine monorepo.

It defines every cross-domain contract object as a passive authority:
JSON schemas, field-level mappings, minimum valid fixtures, a single
registry enumerating all contracts, and a compatibility matrix.

contracts/ contains **no Python code**. It is read as data by integration
tests and by domain implementations.

## How to Read

1. `registry.json` — master list of all contract objects with owner
   domains, schema paths, fixture paths, and consumer domains.
2. `compatibility.json` — which contract version pairs are compatible,
   breaking-change rules, and required validation.
3. `schemas/` — JSON Schema (draft-07) definitions for every contract.
4. `mappings/` — field-level mappings between contracts across domains.
5. `fixtures/` — minimal valid JSON examples matching each schema.

## How to Add a New Contract

1. Define the JSON schema in `schemas/`.
2. Add a registry entry in `registry.json`.
3. Add compatibility rules in `compatibility.json` if the contract has
   consumers in other domains.
4. Add field mappings in `mappings/` if the contract maps to another
   domain's contract.
5. Add a minimal fixture in `fixtures/`.
6. Update integration tests in `integration/tests/` if new validation
   rules are required.

## Versioning Policy

- Every contract schema carries a `schema_version` field.
- Breaking changes (field removal, rename, semantic change) bump the
  major version.
- Additive changes (new optional field) bump the minor version.
- Compatibility rules in `compatibility.json` define which version
  pairs are valid for cross-domain consumption.

## Contributor Guide

- contracts/ must never contain Python source files.
- JSON files must be valid JSON (no comments, no trailing commas).
- Schema files must declare `$schema` and `type`.
- Fixture files must validate against their corresponding schema
  (enforced by `test_schema_parity.py`).
