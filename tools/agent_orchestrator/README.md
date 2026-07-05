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

## Config

| Key | Default | Description |
|-----|---------|-------------|
| `strategist.base_url` | `http://127.0.0.1:1234` | Local proxy URL |
| `strategist.model` | `deepseek-v4-flash` | Model name |
| `worker.command` | `claude` | Claude Code CLI path |
| `gate.check_git_clean` | `false` | Fail if worker modifies tracked files |
| `gate.git_allowed_prefixes` | `[]` | Paths tolerated for new files |

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
