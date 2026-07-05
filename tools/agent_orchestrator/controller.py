#!/usr/bin/env python3
"""controller.py — Minimal MVP Agent Orchestrator.

Main loop:
  1. Check STOP file (if present, shut down gracefully).
  2. Ask strategist (LLM via local proxy) for the next Claude Code task.
  3. Take git snapshot before worker.
  4. Run Claude Code in headless mode as the worker.
  5. Run deterministic gate checks (PASS/FAIL).
  6. On FAIL: revert working tree to pre-iteration state.
  7. Save everything to ``runs/<timestamp>/iter_<n>/``.
  8. Stop on PASS or max iterations.

Usage:
    python controller.py --goal "..." --max-iters 5 --config config.json
    python controller.py --goal "..." --max-iters 1 --dry-run
    python controller.py --list-runs
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

# Ensure the package root is on sys.path for sibling imports
_orchestrator_root = Path(__file__).resolve().parent
if str(_orchestrator_root) not in sys.path:
    sys.path.insert(0, str(_orchestrator_root))

from claude_worker import WorkerConfig, WorkerResult, run_worker
from gate import GateConfig, run_gate
from run_context import RunContext
from strategist_client import StrategistConfig, StrategistResponse, call_strategist


# ── repo root detection ──────────────────────────────────────────────────

_GIT_ROOT_CACHE: Path | None = None


def _detect_repo_root() -> Path:
    """Return the absolute path to the git repository root.

    Uses ``git rev-parse --show-toplevel`` for correctness regardless
    of how deep the orchestrator is nested.
    """
    global _GIT_ROOT_CACHE
    if _GIT_ROOT_CACHE is not None:
        return _GIT_ROOT_CACHE

    try:
        r = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=str(_orchestrator_root),
        )
        if r.returncode == 0:
            _GIT_ROOT_CACHE = Path(r.stdout.strip())
            return _GIT_ROOT_CACHE
    except Exception:
        pass

    # Fallback: assume standard tools/agent_orchestrator/ layout
    _GIT_ROOT_CACHE = _orchestrator_root.parent.parent
    return _GIT_ROOT_CACHE


# ── config loading ───────────────────────────────────────────────────────


def load_config(path: str | os.PathLike[str]) -> dict:
    """Load configuration from YAML or JSON.

    Tries YAML first (if PyYAML is installed), then falls back to JSON.
    """
    path = str(path)
    ext = Path(path).suffix.lower()

    if ext in (".yaml", ".yml"):
        try:
            import yaml  # type: ignore[import-untyped]

            with open(path, encoding="utf-8") as f:
                return yaml.safe_load(f)
        except ImportError:
            print(
                "PyYAML is not installed. Install it with:\n"
                "  pip install pyyaml\n"
                "Or convert the config to JSON and use --config config.json.",
                file=sys.stderr,
            )
            sys.exit(1)
        except Exception as exc:
            print(f"Error reading YAML config: {exc}", file=sys.stderr)
            sys.exit(1)

    with open(path, encoding="utf-8") as f:
        return json.load(f)


def parse_strategist_config(cfg: dict) -> StrategistConfig:
    sc = cfg.get("strategist", {})
    return StrategistConfig(
        provider=sc.get("provider", "anthropic_compatible"),
        base_url=sc.get("base_url", "http://127.0.0.1:1234"),
        model=sc.get("model", "deepseek-v4-flash"),
        temperature=float(sc.get("temperature", 0.2)),
        max_tokens=int(sc.get("max_tokens", 4096)),
    )


def parse_worker_config(cfg: dict) -> WorkerConfig:
    wc = cfg.get("worker", {})
    return WorkerConfig(
        command=wc.get("command", "claude"),
        output_format=wc.get("output_format", "stream-json"),
        timeout_seconds=int(wc.get("timeout_seconds", 300)),
    )


def parse_gate_config(cfg: dict) -> GateConfig:
    gc = cfg.get("gate", {})
    allowed = gc.get("git_allowed_prefixes", None)
    denied = gc.get("git_denied_paths", None)
    report_fields = gc.get("report_required_fields", None)
    return GateConfig(
        test_command=gc.get("test_command", ""),
        required_files=gc.get("required_files", []),
        metrics_file=gc.get("metrics_file", ""),
        check_git_clean=gc.get("check_git_clean", False),
        git_allowed_prefixes=allowed if allowed is not None else [],
        git_denied_paths=denied if denied is not None else [],
        check_report_fields=gc.get("check_report_fields", False),
        report_required_fields=report_fields if report_fields is not None else [],
        synthetic_test_passfile=gc.get("synthetic_test_passfile", ""),
    )


# ── git helpers ──────────────────────────────────────────────────────────

_STOP_FILE = "STOP"  # checked relative to repo root and orchestrator root


def _run_git(args: list[str], cwd: str | os.PathLike[str]) -> subprocess.CompletedProcess:
    """Run a git command and return the result."""
    return subprocess.run(
        ["git"] + args,
        capture_output=True,
        text=True,
        timeout=30,
        cwd=cwd,
    )


def _git_snapshot(repo_root: str | os.PathLike[str]) -> dict[str, str]:
    """Capture pre-iteration git state: HEAD hash, diff, status."""
    head = _run_git(["rev-parse", "HEAD"], cwd=repo_root)
    diff = _run_git(["diff", "--stat"], cwd=repo_root)
    status = _run_git(["status", "--porcelain"], cwd=repo_root)

    return {
        "head": head.stdout.strip() if head.returncode == 0 else "unknown",
        "diff_stat": diff.stdout.strip() if diff.returncode == 0 else "",
        "porcelain": status.stdout.strip() if status.returncode == 0 else "",
    }


def _git_revert_working_tree(repo_root: Path) -> list[str]:
    """Revert tracked-file changes, keeping orchestrator + runs/ evidence.

    Strategy:
      1. ``git checkout -- .`` — revert tracked file modifications.
      2. ``git clean -fd`` — remove new (untracked) files created by the
         worker.  The entire orchestrator directory and its ``runs/``
         subdirectory are excluded so evidence and the tooling itself are
         preserved.

    Returns a list of human-readable action descriptions.
    """
    actions: list[str] = []

    # Step 1: Revert tracked-file changes
    checkout = _run_git(["checkout", "--", "."], cwd=repo_root)
    if checkout.returncode == 0:
        actions.append("reverted tracked changes via git checkout -- .")
    else:
        actions.append(f"git checkout error: {checkout.stderr.strip()[:300]}")
        restore = _run_git(["restore", "."], cwd=repo_root)
        if restore.returncode == 0:
            actions.append("fallback: git restore . succeeded")

    # Step 2: Clean untracked files, preserving the orchestrator directory
    # and its runs/ evidence.  The orchestrator root relative to the repo
    # root is what git status --porcelain shows, so the -e pattern matches.
    orch_rel = _orchestrator_root.relative_to(repo_root)
    exclude_args = ["-e", str(orch_rel).replace("\\", "/") + "/"]

    dry = _run_git(["clean", "-fd", "-n"] + exclude_args, cwd=repo_root)
    dry_out = dry.stdout.strip()[:500] if dry.returncode == 0 else "(dry-run failed)"
    actions.append(f"clean dry-run: {dry_out or '(nothing to remove)'}")

    clean = _run_git(["clean", "-fd"] + exclude_args, cwd=repo_root)
    if clean.returncode == 0:
        actions.append("git clean -fd completed (orchestrator + runs/ preserved)")
    else:
        actions.append(f"git clean error: {clean.stderr.strip()[:300]}")

    return actions


# ── STOP file ────────────────────────────────────────────────────────────


def _check_stop_file(repo_root: Path) -> bool:
    """Return True if a STOP file exists — signals graceful shutdown.

    Checks both the repo root and the orchestrator root.  The file is
    consumed (deleted) after being read so it acts as a one-shot signal.
    """
    candidates = [
        repo_root / _STOP_FILE,
        _orchestrator_root / _STOP_FILE,
    ]
    for p in candidates:
        if p.exists():
            print(f"  [STOP] {p} found — shutting down", file=sys.stderr)
            p.unlink(missing_ok=True)
            return True
    return False


# ── list-runs ────────────────────────────────────────────────────────────


def _list_runs(runs_dir: Path) -> None:
    """Print a summary of all completed runs to stderr."""
    if not runs_dir.exists():
        print("No runs directory found.", file=sys.stderr)
        return

    entries = sorted(
        [d for d in runs_dir.iterdir() if d.is_dir() and d.name != ".gitkeep"],
        reverse=True,
    )
    if not entries:
        print("No completed runs.", file=sys.stderr)
        return

    print(f"\n{'RUN':<30} {'ITER':>5} {'VERDICT':<10}  GOAL", file=sys.stderr)
    print(f"{'─'*30} {'─'*5} {'─'*10}  {'─'*40}", file=sys.stderr)
    for d in entries:
        summary_file = d / "summary.json"
        if summary_file.exists():
            try:
                s = json.loads(summary_file.read_text(encoding="utf-8"))
                iters = s.get("iterations_run", "?")
                verdict = s.get("final_verdict", "?")
                goal = s.get("goal", "")[:50]
            except Exception:
                iters, verdict, goal = "err", "?", ""
        else:
            iters, verdict, goal = "?", "?", ""
        print(f"{d.name:<30} {str(iters):>5} {verdict:<10}  {goal}", file=sys.stderr)


# ── prompt loader ────────────────────────────────────────────────────────


def load_prompt(name: str) -> str:
    """Load a prompt file from the prompts/ directory."""
    path = _orchestrator_root / "prompts" / name
    if path.exists():
        return path.read_text(encoding="utf-8")
    return f"(prompt {name} not found)"


# ── main ─────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="MVP Agent Orchestrator — strategist → worker → gate loop",
    )
    parser.add_argument(
        "--goal",
        required="--list-runs" not in sys.argv,
        help="High-level goal for the orchestrator run",
    )
    parser.add_argument(
        "--max-iters",
        type=int,
        default=5,
        help="Maximum iterations before forced stop (default: 5)",
    )
    parser.add_argument(
        "--config",
        default=str(_orchestrator_root / "config.example.yaml"),
        help="Path to config file (YAML or JSON)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate the loop without calling the strategist or worker",
    )
    parser.add_argument(
        "--list-runs",
        action="store_true",
        help="List all completed runs with verdicts and exit",
    )
    args = parser.parse_args()

    # Handle --list-runs early
    if args.list_runs:
        _list_runs(_orchestrator_root / "runs")
        return

    # Detect repo root once (used for all git operations + worker CWD)
    repo_root = _detect_repo_root()

    # Load config
    cfg = load_config(args.config)

    strategist_cfg = parse_strategist_config(cfg)
    worker_cfg = parse_worker_config(cfg)
    gate_cfg = parse_gate_config(cfg)

    system_prompt = load_prompt("strategist_system.md")
    worker_template = load_prompt("worker_task_template.md")

    # Initialize run context
    ctx = RunContext(goal=args.goal, base_dir=str(_orchestrator_root / "runs"))

    print(f"\n{'#'*60}", file=sys.stderr)
    print(f"  Orchestrator started", file=sys.stderr)
    print(f"  Goal: {args.goal}", file=sys.stderr)
    print(f"  Max iterations: {args.max_iters}", file=sys.stderr)
    print(f"  Run dir: {ctx.run_dir}", file=sys.stderr)
    print(f"  Repo root: {repo_root}", file=sys.stderr)
    print(f"  Dry-run: {args.dry_run}", file=sys.stderr)
    print(f"{'#'*60}\n", file=sys.stderr)

    history: list[dict] = []
    final_verdict = "FAIL"
    iterations_run = 0

    for iteration in range(args.max_iters):
        print(f"\n{'─'*50}", file=sys.stderr)
        print(f"  Iteration {iteration + 1}/{args.max_iters}", file=sys.stderr)
        print(f"{'─'*50}\n", file=sys.stderr)

        # --- Step 0: Check STOP file ---
        if not args.dry_run and _check_stop_file(repo_root):
            final_verdict = "STOPPED"
            ctx.save_summary({
                "iteration": iteration,
                "status": "STOPPED",
                "reason": "STOP file found",
            })
            break

        it_dir = ctx.iter_dir()

        # --- Step 1: Ask the strategist ---
        print(">>> Strategist: requesting next task ...", file=sys.stderr)
        strategist_request = {
            "goal": args.goal,
            "iteration": iteration + 1,
            "max_iters": args.max_iters,
            "history": history[-5:] if history else [],
        }
        ctx.save_strategist_request(strategist_request)

        strategist_resp: StrategistResponse = StrategistResponse()
        if not args.dry_run:
            try:
                strategist_resp = call_strategist(
                    config=strategist_cfg,
                    system_prompt=system_prompt,
                    goal=args.goal,
                    iteration=iteration,
                    max_iters=args.max_iters,
                    history=history,
                )
            except RuntimeError as exc:
                print(f"  [ERROR] {exc}", file=sys.stderr)
                ctx.save_strategist_response({"error": str(exc)})
                ctx.save_summary({
                    "iteration": iteration,
                    "status": "FAILED",
                    "error": str(exc),
                })
                break
        else:
            strategist_resp = StrategistResponse(
                worker_task=f"[DRY-RUN] Create a file at dummy_{iteration}.txt",
                rationale="Testing the orchestrator pipeline",
                expected_artifacts=[f"dummy_{iteration}.txt"],
                success_criteria=["file exists"],
                risk_notes="None (dry run)",
            )

        ctx.save_strategist_response({
            "worker_task": strategist_resp.worker_task,
            "rationale": strategist_resp.rationale,
            "expected_artifacts": strategist_resp.expected_artifacts,
            "success_criteria": strategist_resp.success_criteria,
            "risk_notes": strategist_resp.risk_notes,
        })

        print(f"  Strategist task: {strategist_resp.worker_task[:120]}...", file=sys.stderr)
        print(f"  Rationale: {strategist_resp.rationale[:200]}", file=sys.stderr)

        # --- Step 2: Build worker task ---
        worker_task = worker_template.replace("{{TASK}}", strategist_resp.worker_task)
        ctx.save_worker_task(worker_task)

        # --- Step 2b: Git snapshot before worker ---
        git_before: dict[str, str] = {}
        if not args.dry_run:
            git_before = _git_snapshot(repo_root)
            ctx.save_git_snapshot(git_before)

        # --- Step 3: Run Claude Code worker ---
        worker_result: WorkerResult | None = None
        if not args.dry_run:
            result = run_worker(
                task=worker_task,
                config=worker_cfg,
                log_dir=str(it_dir),
                cwd=str(repo_root),
            )

            ctx.save_worker_log(
                json.dumps({
                    "exit_code": result.exit_code,
                    "log_path": result.raw_log_path,
                    "summary": result.summary,
                    "error": result.error,
                })
            )
            worker_result = result
        else:
            dummy_log = it_dir / "claude_stream.jsonl"
            dummy_log.write_text(
                json.dumps({"type": "dry_run", "message": f"Iteration {iteration}"})
                + "\n",
                encoding="utf-8",
            )
            worker_result = WorkerResult(
                exit_code=0,
                raw_log_path=str(dummy_log),
                summary=f"[DRY-RUN] Simulated Claude Code output for iteration {iteration}",
                error="",
            )

        # --- Step 4: Run gate checks ---
        gate_result = run_gate(
            config=gate_cfg,
            exit_code=worker_result.exit_code,
            worker_log_path=worker_result.raw_log_path,
            repo_root=str(repo_root),
            git_head_before=git_before.get("head", "") if git_before else "",
            git_diff_before=git_before.get("diff_stat", "") if git_before else "",
            worker_summary=worker_result.summary if worker_result else "",
        )

        ctx.save_gate_result({
            "verdict": gate_result.verdict,
            "check_results": gate_result.check_results,
            "reasons": gate_result.reasons,
            "evidence_paths": gate_result.evidence_paths,
        })

        print(f"  Gate verdict: {gate_result.verdict}", file=sys.stderr)
        for r in gate_result.reasons:
            print(f"    - {r}", file=sys.stderr)

        # --- Step 4b: On FAIL, revert working tree (preserve evidence) ---
        if gate_result.verdict == "FAIL" and not args.dry_run:
            print("  [REVERT] Gate FAIL — reverting working tree ...", file=sys.stderr)
            revert_actions = _git_revert_working_tree(repo_root)
            for a in revert_actions:
                print(f"    - {a}", file=sys.stderr)

        # --- Step 5: Record history ---
        history.append({
            "iteration": iteration + 1,
            "worker_task": strategist_resp.worker_task[:200],
            "worker_exit_code": worker_result.exit_code,
            "gate_result": gate_result.verdict,
            "summary": worker_result.summary[:200] if worker_result.summary else "",
        })

        # --- Step 6: Save iteration summary ---
        ctx.save_summary({
            "iteration": iteration + 1,
            "goal": args.goal,
            "strategist_task": strategist_resp.worker_task,
            "worker_exit_code": worker_result.exit_code,
            "gate_verdict": gate_result.verdict,
            "gate_reasons": gate_result.reasons,
            "overall_status": gate_result.verdict,
        })
        iterations_run = iteration + 1

        # --- Stop on PASS ---
        if gate_result.verdict == "PASS":
            final_verdict = "PASS"
            print(f"\n{'='*60}", file=sys.stderr)
            print("  GATE PASSED — stopping early", file=sys.stderr)
            print(f"{'='*60}\n", file=sys.stderr)
            break

        ctx.next_iter()

    else:
        final_verdict = "FAIL"
        print(f"\n{'='*60}", file=sys.stderr)
        print(f"  Max iterations ({args.max_iters}) reached — stopping", file=sys.stderr)
        print(f"{'='*60}\n", file=sys.stderr)

    # Final summary at run level
    final_summary = {
        "goal": args.goal,
        "iterations_run": iterations_run,
        "max_iters": args.max_iters,
        "final_verdict": final_verdict,
        "dry_run": args.dry_run,
        "run_dir": str(ctx.run_dir),
        "repo_root": str(repo_root),
    }

    summary_path = ctx.run_dir / "summary.json"
    summary_path.write_text(
        json.dumps(final_summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print(f"\n{'#'*60}", file=sys.stderr)
    print(f"  Orchestrator finished", file=sys.stderr)
    print(f"  Verdict: {final_verdict}", file=sys.stderr)
    print(f"  Iterations: {iterations_run}", file=sys.stderr)
    print(f"  Run dir: {ctx.run_dir}", file=sys.stderr)
    print(f"  Repo root: {repo_root}", file=sys.stderr)
    print(f"{'#'*60}\n", file=sys.stderr)


if __name__ == "__main__":
    main()
