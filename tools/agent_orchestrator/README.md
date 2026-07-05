# Agent Orchestrator — MVP

Strategist (LLM) → Claude Code worker → deterministic gate loop.
Logs everything under `runs/<timestamp>/`.

## Quick start

```bash
pip install pyyaml   # optional — JSON configs work too
python controller.py --goal "My goal" --max-iters 5 --config config.local.json
python controller.py --goal "Dry run" --max-iters 1 --dry-run
python controller.py --list-runs
```

## Features

- **Strategist**: queries a local proxy (Anthropic-compatible), returns structured JSON
- **Worker**: runs `claude -p "<task>" --output-format stream-json --verbose`
- **Gate**: deterministic PASS/FAIL checks — exit code, files, tests, metrics, git discipline
- **Git snapshot**: records HEAD + diff before each iteration
- **Auto-revert**: on FAIL, `git checkout -- .` + `git clean -fd` (orchestrator preserved)
- **STOP file**: create a `STOP` file in the repo root to gracefully halt

## CLI Flags

| Flag | Default | Description |
|------|---------|-------------|
| `--goal` | required | High-level goal for the run |
| `--max-iters` | `5` | Max iterations before forced stop |
| `--config` | `config.example.yaml` | Config file (YAML or JSON) |
| `--dry-run` | `false` | Simulate without calling LLM/worker |
| `--list-runs` | `false` | List completed runs with verdicts |
| `--retry-exit-codes` | `-1` | Comma-separated exit codes that trigger worker retry |
| `--max-retries-per-iter` | `2` | Max retry attempts per iteration |
| `--keep-last-runs` | `20` | Auto-clean old runs, keep last N (`0` = keep all) |

## Config

| Key | Default | Description |
|-----|---------|-------------|
| `strategist.base_url` | `http://127.0.0.1:1234` | Local proxy URL |
| `strategist.model` | `deepseek-v4-flash` | Model name |
| `worker.command` | `claude` | Claude Code CLI path |
| `worker.timeout_seconds` | `300` | Worker timeout |
| `gate.check_git_clean` | `false` | Fail if worker modifies tracked files |
| `gate.git_allowed_prefixes` | `[]` | Paths tolerated for new files |
| `gate.git_denied_paths` | `[]` | Authority files the worker must never touch |
| `gate.check_report_fields` | `false` | Validate worker summary contains required fields |
| `gate.report_required_fields` | `[]` | Substrings required in worker summary |
| `retry.exit_codes` | `[-1]` | Exit codes that trigger retry |
| `retry.max_retries_per_iter` | `2` | Max retries per iteration |
| `cleanup.keep_last_runs` | `20` | Keep last N runs on startup |

## Output

```
runs/<ts>/iter_<n>/
  strategist_request.json  strategist_response.json
  worker_task.txt          claude_stream.jsonl
  git_snapshot.json        gate_result.json
  summary.json
```

## Safety

- On FAIL, tracked changes are reverted via `git checkout -- .`.
  The `tools/agent_orchestrator/` directory is excluded from clean.
- Uncommitted work outside `tools/agent_orchestrator/` may be cleaned.
- Run on a dedicated branch for experimental setups.
