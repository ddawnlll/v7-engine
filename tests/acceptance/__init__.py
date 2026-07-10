"""Acceptance tests for V7 Engine integration requirements.

These tests validate end-to-end wiring of production pipelines:
- #267: Pipeline row identity and canonical alignment
- #315: Funding event persistence, loader, and label chain
- #304: Full pipeline economic-truth E2E (requires #267 + #315 fixes)

Tests use `xfail(strict=True)` where the current head (83ebadf) has
known bugs that the corresponding PR will fix. After #267/#315 are
rebase-merged, these xfail markers should be removed and tests must PASS.

No production fixes are contained in this test suite.
"""
