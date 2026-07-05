"""Tests for policycritic.critic — IQL critic + review."""

from policycritic.critic import CriticBuffer, IQLCritic, review_action, ACTIONS


class TestCriticBuffer:
    def test_add_and_len(self):
        buf = CriticBuffer(max_size=100)
        assert len(buf) == 0
        buf.add({"rsi": 50}, 0, 1.0, {"rsi": 55})
        assert len(buf) == 1

    def test_max_size(self):
        buf = CriticBuffer(max_size=2)
        buf.add({"a": 1}, 0, 1.0, {"a": 2})
        buf.add({"a": 2}, 1, 0.5, {"a": 3})
        buf.add({"a": 3}, 2, -0.5, {"a": 4})
        assert len(buf) == 2

    def test_sample(self):
        buf = CriticBuffer(max_size=100)
        for i in range(20):
            buf.add({"f": float(i)}, i % 3, float(i), {"f": float(i + 1)})
        batch = buf.sample(5)
        assert len(batch["states"]) == 5
        assert len(batch["actions"]) == 5


class TestIQLCritic:
    def test_predict_before_fit(self):
        critic = IQLCritic()
        q = critic.predict({"rsi": 50, "vol": 0.5})
        assert all(v == 0.0 for v in q.values())
        assert set(q.keys()) == {"LONG_NOW", "SHORT_NOW", "NO_TRADE"}

    def test_update_and_predict(self):
        critic = IQLCritic()
        buf = CriticBuffer(max_size=1000)
        for i in range(100):
            buf.add({"rsi": 50 + i * 0.1}, i % 3, 1.0 if i % 3 == 0 else -0.5, {"rsi": 50 + (i + 1) * 0.1})
        metrics = critic.update(buf, batch_size=32)
        assert "loss" in metrics
        assert metrics["samples"] == 32
        q = critic.predict({"rsi": 55})
        assert any(v != 0.0 for v in q.values())


class TestReviewAction:
    def test_not_ready_allows(self):
        critic = IQLCritic()
        review = review_action(critic, {"rsi": 50}, "LONG_NOW", 0.7)
        assert review["critic_verdict"] == "ALLOW"
        assert review["is_advisory"] is True

    def test_veto_when_q_negative(self):
        critic = IQLCritic()
        buf = CriticBuffer(max_size=100)
        for i in range(50):
            buf.add({"rsi": float(i)}, 0, -0.5, {"rsi": float(i + 1)})
        critic.update(buf, batch_size=20)
        review = review_action(critic, {"rsi": 25}, "LONG_NOW", 0.7)
        assert review["critic_verdict"] in ("VETO_TO_NO_TRADE", "ALLOW")
        assert "critic_version" in review
