"""claude_worker.py — Runs Claude Code CLI as the worker agent."""
from __future__ import annotations
import os, shlex, subprocess, sys
from dataclasses import dataclass
from pathlib import Path

@dataclass
class WorkerResult:
    exit_code: int
    raw_log_path: str
    summary: str = ""
    error: str = ""

@dataclass
class WorkerConfig:
    command: str = "claude"
    output_format: str = "stream-json"
    timeout_seconds: int = 300

def run_worker(task: str, config: WorkerConfig, log_dir: str | os.PathLike[str], cwd: str | os.PathLike[str] | None = None) -> WorkerResult:
    log_path = Path(log_dir) / "claude_stream.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [config.command, "-p", task, "--output-format", config.output_format]
    if config.output_format == "stream-json": cmd.append("--verbose")
    cmd.append("--allow-dangerously-skip-permissions")
    cmd.append("--dangerously-skip-permissions")
    print(f"\n{'='*60}\n  Worker: {' '.join(shlex.quote(c) for c in cmd)[:120]}\n  Log:    {log_path}\n{'='*60}\n", file=sys.stderr)
    raw_lines, summary, error, proc = [], "", "", None
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1, cwd=cwd)
        if proc.stdout:
            for line in iter(proc.stdout.readline, ""): raw_lines.append(line); sys.stderr.write(line); sys.stderr.flush()
        stderr_text = proc.stderr.read() if proc.stderr else ""
        proc.wait(timeout=config.timeout_seconds)
        ec = proc.returncode
        summary = _extract_summary(raw_lines, stderr_text)
        if ec != 0: error = stderr_text[:2048] if stderr_text else f"exit code {ec}"
    except subprocess.TimeoutExpired:
        if proc: proc.kill()
        ec, error = -1, f"Worker timed out after {config.timeout_seconds}s"
    except FileNotFoundError:
        ec, error = -1, f"Command '{config.command}' not found"
    except Exception as e:
        ec, error = -1, f"Worker error: {e}"
    log_path.write_text("".join(raw_lines), encoding="utf-8")
    return WorkerResult(exit_code=ec, raw_log_path=str(log_path), summary=summary, error=error)

def _extract_summary(stdout_lines: list[str], stderr: str) -> str:
    full = "".join(stdout_lines)
    lines = full.strip().splitlines()
    tail = "\n".join(lines[-20:])
    if len(tail.strip()) > 50 and not tail.strip().startswith("{"): return tail[:2048]
    best = ""
    for line in lines:
        s = line.strip()
        if s and not s.startswith("{") and not s.startswith("[") and len(s) > len(best): best = s
    return best[:2048] if best else "(no summary)"
