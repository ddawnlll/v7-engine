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


def run_worker(
    task: str,
    config: WorkerConfig,
    log_dir: str | os.PathLike[str],
    cwd: str | os.PathLike[str] | None = None,
) -> WorkerResult:
    log_path = Path(log_dir) / "claude_stream.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [config.command, "-p", task, "--output-format", config.output_format]
    if config.output_format == "stream-json":
        cmd.append("--verbose")
    cmd.append("--permission-mode")
    cmd.append("bypassPermissions")
    print(
        f"\n{'='*60}\n  Worker: {' '.join(shlex.quote(c) for c in cmd)[:120]}\n  Log:    {log_path}\n{'='*60}\n",
        file=sys.stderr,
    )

    raw_lines: list[str] = []
    summary = ""
    error = ""
    proc: subprocess.Popen[str] | None = None
    ec: int = -1

    try:
        print("Worker starting...", file=sys.stderr)
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,  # merge stderr into stdout — no pipe deadlock
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            cwd=cwd,
        )
        if proc.stdout:
            for line in iter(proc.stdout.readline, ""):
                raw_lines.append(line)
                sys.stderr.write(line)
                sys.stderr.flush()
        proc.wait(timeout=config.timeout_seconds)
        ec = proc.returncode
        summary = _extract_summary(raw_lines)
        if ec != 0:
            error = f"exit code {ec}"
        print(f"Worker exited with code {ec}", file=sys.stderr)
    except subprocess.TimeoutExpired:
        print("Worker timed out", file=sys.stderr)
        if proc:
            proc.kill()
            # Drain remaining output to prevent hang on kill()
            if proc.stdout:
                proc.stdout.read()
        ec, error = -1, f"Worker timed out after {config.timeout_seconds}s"
    except FileNotFoundError:
        ec, error = -1, f"Command '{config.command}' not found"
    except Exception as e:
        ec, error = -1, f"Worker error: {e}"

    log_path.write_text("".join(raw_lines), encoding="utf-8")
    return WorkerResult(
        exit_code=ec, raw_log_path=str(log_path), summary=summary, error=error
    )


def _extract_summary(stdout_lines: list[str]) -> str:
    """Extract a meaningful summary from worker output lines.

    Prefers the last non-JSON, non-trivial line from the output tail.
    Falls back to the longest non-JSON line in the full output.
    """
    if not stdout_lines:
        return "(no summary)"

    lines = [l.rstrip("\n\r") for l in stdout_lines]

    def _is_json_like(s: str) -> bool:
        stripped = s.strip()
        return bool(
            stripped
            and (
                stripped.startswith(("{", "["))
                or stripped.startswith('"')
            )
        )

    # Walk backwards, skip JSON-only lines, find last meaningful text line
    best = ""
    for line in reversed(lines):
        s = line.strip()
        if s and not _is_json_like(s):
            best = s
            break

    # Fallback: longest non-JSON line from entire output
    if not best:
        for line in lines:
            s = line.strip()
            if s and not _is_json_like(s) and len(s) > len(best):
                best = s

    if not best:
        return "(no summary)"

    return best[:2048]
