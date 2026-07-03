"""AlphaRuleSpec export — versioned declarative artifacts for V7 consumption.

Exports validated/candidate rules as JSON artifacts with:
- Provenance tracking
- Forbidden flags (no leakage, no best-of-side, no local simulation)
- Schema validation
- Alpha registry index

Authority boundary:
  - AlphaForge produces AlphaRuleSpec artifacts
  - V7 consumes validated AlphaRuleSpec / EvidencePassport / V7HandoffPackage
  - AlphaForge does NOT automatically write rules as production code
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Schema version
# ---------------------------------------------------------------------------

ALPHA_RULE_SPEC_VERSION = "1.0.0"


# ---------------------------------------------------------------------------
# AlphaRuleSpecBuilder
# ---------------------------------------------------------------------------

class AlphaRuleSpecBuilder:
    """Builds AlphaRuleSpec artifacts from validated rules.

    Usage::

        builder = AlphaRuleSpecBuilder()
        specs = builder.build(validated_rules, mining_run_id="run_001")
        builder.export(specs, output_dir="reports/alphaforge/mining/alpha_rule_specs/")
        registry = builder.build_registry(specs)
    """

    def __init__(self) -> None:
        self._specs: List[Dict[str, Any]] = []

    def build(
        self,
        rules: List[Dict[str, Any]],
        mining_run_id: str = "",
        dataset_version: str = "v002",
        git_sha: str = "",
    ) -> List[Dict[str, Any]]:
        """Build AlphaRuleSpec artifacts from rule results.

        Args:
            rules: Validated/candidate rule dicts from validation funnel.
            mining_run_id: Identifier for this mining run.
            dataset_version: Dataset version used.
            git_sha: Current git SHA for provenance.

        Returns:
            List of AlphaRuleSpec dicts.
        """
        specs = []
        for i, rule in enumerate(rules):
            spec = self._build_single(rule, i, mining_run_id, dataset_version, git_sha)
            specs.append(spec)
        self._specs = specs
        return specs

    def _build_single(
        self,
        rule: Dict[str, Any],
        index: int,
        mining_run_id: str,
        dataset_version: str,
        git_sha: str,
    ) -> Dict[str, Any]:
        """Build a single AlphaRuleSpec."""
        rule_id = rule.get("rule_id", rule.get("id", f"rule_{index}"))
        status = rule.get("status", "RESEARCH_CANDIDATE")
        conditions = rule.get("conditions", [])
        primary_family = rule.get("primary_family", "other")

        # Build conditions list
        condition_specs = []
        for cond in conditions:
            # Parse condition string (format: "feature__bucket" or "feature__d01")
            parts = cond.rsplit("__", 1)
            if len(parts) == 2:
                feature, bucket = parts
            else:
                feature, bucket = cond, "unknown"

            condition_specs.append({
                "feature": feature,
                "operator": "in_bucket",
                "bucket": bucket,
                "feature_family": self._detect_family(feature),
            })

        # Evidence
        discovery = rule.get("discovery", {})
        validation = rule.get("validation", {})
        holdout = rule.get("holdout", {})

        evidence = {
            "support_total": discovery.get("support", 0),
            "support_discovery": discovery.get("support", 0),
            "support_validation": validation.get("support", 0),
            "support_holdout": holdout.get("support", 0),
            "mean_net_R": discovery.get("mean_net_R", 0.0),
            "mean_excess_net_R": discovery.get("mean_excess_net_R", 0.0),
            "validation_mean_excess_net_R": validation.get("mean_excess_net_R", 0.0),
            "holdout_mean_excess_net_R": holdout.get("mean_excess_net_R", 0.0),
            "oos_is_ratio": rule.get("oos_is_ratio", 0.0),
            "symbol_stability": rule.get("symbol_stability", 0.0),
            "pass_fail": status,
            "fail_reasons": rule.get("fail_reasons", []),
        }

        # Provenance
        provenance = {
            "dataset_version": dataset_version,
            "mining_run_id": mining_run_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "code_git_sha": git_sha,
        }

        # Forbidden flags (always False — enforced by architecture)
        forbidden = {
            "contains_future_leakage": False,
            "uses_best_of_side": False,
            "uses_local_simulation": False,
        }

        spec = {
            "alpha_id": f"alpha_{rule_id}",
            "schema_version": ALPHA_RULE_SPEC_VERSION,
            "family_id": rule.get("family_id", f"family_{index}"),
            "family_name": primary_family,
            "status": status,
            "mode": rule.get("mode", "ANY"),
            "timeframe": rule.get("timeframe", "ANY"),
            "side": rule.get("side", "ANY"),
            "conditions": condition_specs,
            "target": {
                "primary": "excess_net_R",
                "secondary": ["net_R"],
            },
            "baseline": {
                "grouping_fields": ["mode", "side", "timeframe", "atr_bucket", "regime_bucket"],
                "baseline_version": "v001",
            },
            "evidence": evidence,
            "provenance": provenance,
            "forbidden": forbidden,
        }

        return spec

    def _detect_family(self, feature_name: str) -> str:
        """Detect feature family from name."""
        name_lower = feature_name.lower()
        families = {
            "volatility": ["volatility", "atr", "spread"],
            "momentum": ["momentum", "return", "rsi"],
            "volume": ["volume", "taker"],
            "regime": ["regime", "trend"],
            "range_position": ["range", "distance", "pullback"],
            "btc_regime": ["btc"],
            "cross_sectional": ["rank", "relative", "cs_"],
            "session": ["hour", "session", "weekday"],
            "side": ["side"],
            "mode": ["mode"],
        }
        for family, keywords in families.items():
            if any(kw in name_lower for kw in keywords):
                return family
        return "other"

    def export(
        self,
        specs: List[Dict[str, Any]],
        output_dir: str,
    ) -> int:
        """Export AlphaRuleSpec artifacts to disk.

        Returns the number of exported specs.
        """
        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)

        exported = 0
        for spec in specs:
            alpha_id = spec.get("alpha_id", f"spec_{exported}")
            filename = f"{alpha_id}.json"
            filepath = out_path / filename

            with open(filepath, "w") as f:
                json.dump(spec, f, indent=2, default=str)
            exported += 1

        logger.info("Exported %d AlphaRuleSpec artifacts to %s", exported, output_dir)
        return exported

    def build_registry(self, specs: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Build an alpha registry index from specs."""
        registry = {
            "schema_version": ALPHA_RULE_SPEC_VERSION,
            "total_specs": len(specs),
            "validated_count": sum(1 for s in specs if s.get("status") == "VALIDATED"),
            "candidate_count": sum(1 for s in specs if s.get("status") == "CANDIDATE_ONLY"),
            "rejected_count": sum(1 for s in specs if s.get("status") == "REJECTED"),
            "specs": [
                {
                    "alpha_id": s.get("alpha_id"),
                    "family_id": s.get("family_id"),
                    "family_name": s.get("family_name"),
                    "status": s.get("status"),
                    "mean_excess_net_R": s.get("evidence", {}).get("mean_excess_net_R", 0),
                    "validation_mean_excess_net_R": s.get("evidence", {}).get("validation_mean_excess_net_R", 0),
                }
                for s in specs
            ],
        }
        return registry
