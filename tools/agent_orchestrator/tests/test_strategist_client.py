"""Tests for strategist_client.py -- parsing LLM responses."""

from strategist_client import _parse


def test_parse_v1_messages():
    """_parse handles /v1/messages format (Claude API)."""
    resp = {
        "content": [
            {
                "type": "text",
                "text": '{"worker_task": "test task", "rationale": "testing",'
                ' "expected_artifacts": [], "success_criteria": [], "risk_notes": ""}',
            }
        ]
    }
    result = _parse(resp, "/v1/messages")
    assert result.worker_task == "test task"
    assert result.rationale == "testing"
    assert result.expected_artifacts == []
    assert result.success_criteria == []


def test_parse_v1_chat():
    """_parse handles /v1/chat/completions format (OpenAI-compatible)."""
    resp = {
        "choices": [
            {
                "message": {
                    "content": '{"worker_task": "chat task", "rationale": "chat testing",'
                    ' "expected_artifacts": ["file1"], "success_criteria": ["works"],'
                    ' "risk_notes": "none"}',
                }
            }
        ]
    }
    result = _parse(resp, "/v1/chat/completions")
    assert result.worker_task == "chat task"
    assert result.rationale == "chat testing"
    assert result.expected_artifacts == ["file1"]
    assert result.success_criteria == ["works"]


def test_parse_json_backticks():
    """Input with ```json wrapping is stripped before parsing."""
    txt = '```json\n{"worker_task": "backtick task", "rationale": "backtick testing"}\n```'
    resp = {"content": [{"type": "text", "text": txt}]}
    result = _parse(resp, "/v1/messages")
    assert result.worker_task == "backtick task"
    assert result.rationale == "backtick testing"


def test_parse_non_json():
    """Non-JSON input returns worker_task with raw text."""
    txt = "Some plain text response without JSON structure"
    resp = {"content": [{"type": "text", "text": txt}]}
    result = _parse(resp, "/v1/messages")
    assert result.worker_task == txt
