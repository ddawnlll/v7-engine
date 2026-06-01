"""
integration/adapters — Cross-domain adapter stubs.

These adapters define the integration points between domains.
Real implementations belong to later phases (simulation S3, alphaforge P2, v7 phase 2).

Rules:
- Adapters must be importable without importing simulation, alphaforge, or v7.
- Adapter methods raise NotImplementedError until real implementations exist.
- Adapters use stdlib typing only.
"""
