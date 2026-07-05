"""Tests for v7.policy_critic.metrics — CriticMetrics and pipeline."""

import pytest

from v7.policy_critic.metrics import (
    VALID_VERDICTS,
    CriticMetrics,
    CriticMetricsPipeline,
)


class TestCriticMetrics:
    """Test CriticMetrics dataclass construction and defaults."""

    def test_defaults(self):
        """All fields default to zero/empty values."""
        m = CriticMetrics()
        assert m.critic_value_long == 0.0
        assert m.critic_value_short == 0.0
        assert m.critic_verdict == "NOT_EVALUATED"
        assert m.conformal_p_value == 0.0
        assert m.regret_r == 0.0
        assert m.expected_r == 0.0
        assert m.timestamp_utc == ""
        assert m.symbol == ""
        assert m.model_scope == "shadow"

    def test_frozen(self):
        """CriticMetrics is frozen (immutable)."""
        m = CriticMetrics(symbol="BTCUSDT")
        with pytest.raises(AttributeError):
            m.symbol = "ETHUSDT"  # type: ignore[misc]

    def test_kwargs_construction(self):
        """Fields can be set via constructor kwargs."""
        m = CriticMetrics(
            critic_value_long=0.75,
            critic_value_short=-0.20,
            critic_verdict="CORRECT",
            conformal_p_value=0.92,
            regret_r=0.12,
            expected_r=0.55,
            timestamp_utc="2026-07-05T12:00:00Z",
            symbol="BTCUSDT",
            model_scope="v1_swing",
        )
        assert m.critic_value_long == 0.75
        assert m.critic_value_short == -0.20
        assert m.critic_verdict == "CORRECT"
        assert m.conformal_p_value == 0.92
        assert m.regret_r == 0.12
        assert m.expected_r == 0.55
        assert m.symbol == "BTCUSDT"
        assert m.model_scope == "v1_swing"


class TestCriticMetricsPipelineIngest:
    """Test CriticMetricsPipeline.ingest()."""

    def _decision_event(self, **overrides) -> dict:
        """Build a minimal DecisionEvent dict for testing."""
        base = {
            "decision_event_id": "de_test_001",
            "symbol": "BTCUSDT",
            "event_type": "ENTER_LONG",
            "critic_review": {
                "critic_value_LONG": 0.85,
                "critic_value_SHORT": -0.30,
                "critic_verdict": "CORRECT",
                "conformal_p_value": 0.88,
                "regret_r": 0.05,
                "expected_r": 0.60,
                "model_scope": "v1_swing",
            },
        }
        base.update(overrides)
        return base

    def test_ingest_basic(self):
        """Happy path: ingest with full critic_review."""
        event = self._decision_event()
        metrics = CriticMetricsPipeline.ingest(event)
        assert isinstance(metrics, CriticMetrics)
        assert metrics.critic_value_long == 0.85
        assert metrics.critic_value_short == -0.30
        assert metrics.critic_verdict == "CORRECT"
        assert metrics.conformal_p_value == 0.88
        assert metrics.regret_r == 0.05
        assert metrics.expected_r == 0.60
        assert metrics.symbol == "BTCUSDT"
        assert metrics.model_scope == "v1_swing"
        assert metrics.timestamp_utc  # non-empty ISO string

    def test_ingest_missing_critic_review(self):
        """No critic_review -> shadow mode defaults."""
        event = self._decision_event()
        del event["critic_review"]
        metrics = CriticMetricsPipeline.ingest(event)
        assert metrics.critic_value_long == 0.0
        assert metrics.critic_value_short == 0.0
        assert metrics.critic_verdict == "NOT_EVALUATED"
        assert metrics.conformal_p_value == 0.0
        assert metrics.model_scope == "shadow"

    def test_ingest_empty_critic_review(self):
        """Empty critic_review dict -> zero/NOT_EVALUATED defaults."""
        event = self._decision_event(critic_review={})
        metrics = CriticMetricsPipeline.ingest(event)
        assert metrics.critic_verdict == "NOT_EVALUATED"
        assert metrics.critic_value_long == 0.0
        assert metrics.model_scope == "shadow"

    def test_ingest_partial_critic_review(self):
        """Partial critic_review -> missing fields defaulted."""
        event = self._decision_event(critic_review={"critic_verdict": "WRONG"})
        metrics = CriticMetricsPipeline.ingest(event)
        assert metrics.critic_verdict == "WRONG"
        assert metrics.critic_value_long == 0.0  # default
        assert metrics.regret_r == 0.0  # default

    def test_ingest_missing_required_fields(self):
        """Missing decision_event_id or symbol raises ValueError."""
        event = self._decision_event()
        del event["decision_event_id"]
        with pytest.raises(ValueError, match="missing required fields"):
            CriticMetricsPipeline.ingest(event)

    def test_ingest_missing_symbol(self):
        """Missing symbol raises ValueError."""
        event = self._decision_event()
        del event["symbol"]
        with pytest.raises(ValueError, match="missing required fields"):
            CriticMetricsPipeline.ingest(event)

    def test_ingest_timestamp_is_set(self):
        """Timestamp is always set to current UTC."""
        event = self._decision_event()
        metrics = CriticMetricsPipeline.ingest(event)
        assert "T" in metrics.timestamp_utc
        assert metrics.timestamp_utc.endswith("+00:00") or "+" in metrics.timestamp_utc or "Z" in metrics.timestamp_utc


class TestCriticMetricsPipelineToReviewSchema:
    """Test CriticMetricsPipeline.to_review_schema()."""

    def test_to_review_schema_keys(self):
        """Output dict contains all expected PolicyCriticReview keys."""
        metrics = CriticMetrics(
            critic_value_long=0.75,
            critic_value_short=-0.20,
            critic_verdict="CORRECT",
            conformal_p_value=0.92,
            regret_r=0.12,
            expected_r=0.55,
            timestamp_utc="2026-07-05T12:00:00Z",
            symbol="BTCUSDT",
            model_scope="v1_swing",
        )
        out = CriticMetricsPipeline.to_review_schema(metrics)
        expected_keys = {
            "review_id",
            "symbol",
            "model_scope",
            "timestamp",
            "critic_value_LONG",
            "critic_value_SHORT",
            "critic_verdict",
            "conformal_p_value",
            "regret_r",
            "expected_r",
        }
        assert set(out.keys()) == expected_keys

    def test_to_review_schema_values(self):
        """Output dict preserves metric values."""
        metrics = CriticMetrics(
            critic_value_long=0.75,
            critic_value_short=-0.20,
            critic_verdict="CORRECT",
            conformal_p_value=0.92,
            regret_r=0.12,
            expected_r=0.55,
            timestamp_utc="2026-07-05T12:00:00Z",
            symbol="BTCUSDT",
            model_scope="v1_swing",
        )
        out = CriticMetricsPipeline.to_review_schema(metrics)
        assert out["symbol"] == "BTCUSDT"
        assert out["model_scope"] == "v1_swing"
        assert out["critic_value_LONG"] == 0.75
        assert out["critic_value_SHORT"] == -0.20
        assert out["critic_verdict"] == "CORRECT"
        assert out["conformal_p_value"] == 0.92
        assert out["regret_r"] == 0.12
        assert out["expected_r"] == 0.55

    def test_to_review_schema_generates_review_id(self):
        """review_id is generated with symbol prefix."""
        metrics = CriticMetrics(symbol="ETHUSDT", model_scope="shadow")
        out = CriticMetricsPipeline.to_review_schema(metrics)
        assert out["review_id"].startswith("pcr-ETHUSDT-")
        assert len(out["review_id"]) > len("pcr-ETHUSDT-")

    def test_to_review_schema_default_metrics(self):
        """Default metrics produce valid schema output."""
        metrics = CriticMetrics()
        out = CriticMetricsPipeline.to_review_schema(metrics)
        assert out["critic_value_LONG"] == 0.0
        assert out["critic_verdict"] == "NOT_EVALUATED"
        assert out["conformal_p_value"] == 0.0
        assert out["regret_r"] == 0.0


class TestCriticMetricsPipelineValidate:
    """Test CriticMetricsPipeline.validate()."""

    def test_valid_metrics(self):
        """All valid fields -> empty issues list."""
        metrics = CriticMetrics(
            critic_verdict="CORRECT",
            conformal_p_value=0.5,
            timestamp_utc="2026-07-05T12:00:00Z",
            symbol="BTCUSDT",
            model_scope="v1_swing",
        )
        issues = CriticMetricsPipeline.validate(metrics)
        assert issues == []

    def test_invalid_verdict(self):
        """Invalid verdict reports issue."""
        metrics = CriticMetrics(critic_verdict="INVALID", symbol="X", model_scope="x")
        issues = CriticMetricsPipeline.validate(metrics)
        assert any("Invalid critic_verdict" in i for i in issues)

    def test_empty_symbol(self):
        """Empty symbol reports issue."""
        metrics = CriticMetrics(symbol="", model_scope="x")
        issues = CriticMetricsPipeline.validate(metrics)
        assert any("symbol must be non-empty" in i for i in issues)

    def test_empty_model_scope(self):
        """Empty model_scope reports issue."""
        metrics = CriticMetrics(symbol="X", model_scope="")
        issues = CriticMetricsPipeline.validate(metrics)
        assert any("model_scope must be non-empty" in i for i in issues)

    def test_conformal_p_value_out_of_range_negative(self):
        """Negative conformal_p_value reports issue."""
        metrics = CriticMetrics(
            symbol="X", model_scope="x", conformal_p_value=-0.1
        )
        issues = CriticMetricsPipeline.validate(metrics)
        assert any("conformal_p_value" in i for i in issues)

    def test_conformal_p_value_out_of_range_over_one(self):
        """conformal_p_value > 1.0 reports issue."""
        metrics = CriticMetrics(
            symbol="X", model_scope="x", conformal_p_value=1.5
        )
        issues = CriticMetricsPipeline.validate(metrics)
        assert any("conformal_p_value" in i for i in issues)

    def test_invalid_timestamp(self):
        """Non-ISO timestamp reports issue."""
        metrics = CriticMetrics(
            symbol="X",
            model_scope="x",
            timestamp_utc="not-a-timestamp",
        )
        issues = CriticMetricsPipeline.validate(metrics)
        assert any("timestamp_utc" in i for i in issues)

    def test_all_verdicts_valid(self):
        """All VALID_VERDICTS pass validation."""
        for verdict in VALID_VERDICTS:
            metrics = CriticMetrics(
                critic_verdict=verdict,
                symbol="X",
                model_scope="x",
            )
            issues = CriticMetricsPipeline.validate(metrics)
            assert not any("verdict" in i for i in issues), f"verdict {verdict} failed"

    def test_conformal_boundary_zero(self):
        """conformal_p_value == 0.0 is valid."""
        metrics = CriticMetrics(
            symbol="X", model_scope="x", conformal_p_value=0.0
        )
        issues = CriticMetricsPipeline.validate(metrics)
        assert not any("conformal_p_value" in i for i in issues)

    def test_conformal_boundary_one(self):
        """conformal_p_value == 1.0 is valid."""
        metrics = CriticMetrics(
            symbol="X", model_scope="x", conformal_p_value=1.0
        )
        issues = CriticMetricsPipeline.validate(metrics)
        assert not any("conformal_p_value" in i for i in issues)

    def test_empty_timestamp_no_validation(self):
        """Empty timestamp is not validated (optional field)."""
        metrics = CriticMetrics(
            symbol="X",
            model_scope="x",
            timestamp_utc="",
        )
        issues = CriticMetricsPipeline.validate(metrics)
        assert not any("timestamp" in i.lower() for i in issues)
