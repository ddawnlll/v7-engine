"""Tests for controller.py -- config loading and parsing."""

import json

from controller import load_config, parse_strategist_config, parse_worker_config, parse_gate_config
from strategist_client import StrategistConfig
from claude_worker import WorkerConfig
from gate import GateConfig


def test_load_config_json(tmp_path):
    """load_config parses a JSON config file."""
    data = {"strategist": {"model": "test-model"}, "worker": {"command": "test-cmd"}}
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps(data), encoding="utf-8")
    result = load_config(str(config_file))
    assert result["strategist"]["model"] == "test-model"
    assert result["worker"]["command"] == "test-cmd"


def test_parse_strategist_config():
    """Dict -> StrategistConfig with provided values."""
    cfg = {
        "strategist": {
            "provider": "custom",
            "base_url": "http://localhost:8080",
            "model": "gpt-4",
            "temperature": 0.5,
            "max_tokens": 2048,
        }
    }
    result = parse_strategist_config(cfg)
    assert isinstance(result, StrategistConfig)
    assert result.provider == "custom"
    assert result.base_url == "http://localhost:8080"
    assert result.model == "gpt-4"
    assert result.temperature == 0.5
    assert result.max_tokens == 2048


def test_parse_strategist_config_defaults():
    """Empty dict -> StrategistConfig with defaults."""
    result = parse_strategist_config({})
    assert result.provider == "anthropic_compatible"
    assert result.base_url == "http://127.0.0.1:1234"
    assert result.model == "deepseek-v4-flash"
    assert result.temperature == 0.2
    assert result.max_tokens == 4096


def test_parse_worker_config():
    """Dict -> WorkerConfig with provided values."""
    cfg = {"worker": {"command": "my-claude", "output_format": "json", "timeout_seconds": 600}}
    result = parse_worker_config(cfg)
    assert isinstance(result, WorkerConfig)
    assert result.command == "my-claude"
    assert result.output_format == "json"
    assert result.timeout_seconds == 600


def test_parse_worker_config_defaults():
    """Empty dict -> WorkerConfig with defaults."""
    result = parse_worker_config({})
    assert result.command == "claude"
    assert result.output_format == "stream-json"
    assert result.timeout_seconds == 300


def test_parse_gate_config():
    """Dict -> GateConfig with provided values."""
    cfg = {
        "gate": {
            "test_command": "pytest",
            "required_files": ["output.txt"],
            "metrics_file": "metrics.json",
            "check_git_clean": True,
            "git_allowed_prefixes": ["candidates/"],
            "git_denied_paths": ["v7/evaluation.py"],
            "check_report_fields": True,
            "report_required_fields": ["train_start"],
            "synthetic_test_passfile": ".passed",
        }
    }
    result = parse_gate_config(cfg)
    assert isinstance(result, GateConfig)
    assert result.test_command == "pytest"
    assert result.required_files == ["output.txt"]
    assert result.metrics_file == "metrics.json"
    assert result.check_git_clean is True
    assert result.git_allowed_prefixes == ["candidates/"]
    assert result.git_denied_paths == ["v7/evaluation.py"]
    assert result.check_report_fields is True
    assert result.report_required_fields == ["train_start"]
    assert result.synthetic_test_passfile == ".passed"


def test_parse_gate_config_defaults():
    """Empty dict -> GateConfig with defaults."""
    result = parse_gate_config({})
    assert result.test_command == ""
    assert result.required_files == []
    assert result.metrics_file == ""
    assert result.check_git_clean is False
    assert result.git_allowed_prefixes == []
    assert result.git_denied_paths == []
    assert result.check_report_fields is False
    assert result.report_required_fields == []
    assert result.synthetic_test_passfile == ""
