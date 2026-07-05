"""gate.py — Deterministic gate checks for PASS/FAIL.

Three layers:
  A. Mechanical safety  — exit code, log, required files, test command, metrics
  B. Git discipline     — head saved, no tracked mods, allowed prefixes, denied paths
  C. Research discipline— report fields, synthetic signal test
"""
from __future__ import annotations
import json, os, re, subprocess
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class GateConfig:
    # Layer A — mechanical
    test_command: str = ""
    required_files: list[str] = field(default_factory=list)
    metrics_file: str = ""

    # Layer B — git
    check_git_clean: bool = False
    git_allowed_prefixes: list[str] = field(default_factory=list)
    git_denied_paths: list[str] = field(default_factory=list)
    """Files that must NEVER be touched by the worker, even if inside an
    allowed prefix.  Each entry is a repo-root-relative path prefix."""

    # Layer C — research discipline
    check_report_fields: bool = False
    report_required_fields: list[str] = field(default_factory=list)
    """Substrings the worker's completion summary must contain (e.g.
    ``train_start``, ``n_combinations``, ``metric``)."""
    synthetic_test_passfile: str = ""
    """Path (relative to repo root) to a sentinel file that proves a
    synthetic signal test passed.  Typically set only when authority
    files are in ``git_denied_paths``."""


@dataclass
class GateResult:
    verdict: str
    check_results: dict[str, bool] = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)
    evidence_paths: list[str] = field(default_factory=list)


def run_gate(
    config: GateConfig,
    exit_code: int,
    worker_log_path: str,
    repo_root: str | os.PathLike[str] | None = None,
    git_head_before: str = "",
    git_diff_before: str = "",
    worker_summary: str = "",
) -> GateResult:
    root = Path(repo_root).resolve() if repo_root else Path.cwd().resolve()
    checks, reasons, evidence = {}, [], []

    # ── Layer A ──────────────────────────────────────────────────────────

    # 1: exit code
    checks["exit_code_ok"] = exit_code == 0
    reasons.append("Worker exited cleanly" if exit_code == 0 else f"Worker exited with code {exit_code}")

    # 2: log exists
    lp = Path(worker_log_path)
    checks["log_exists"] = lp.exists() and lp.stat().st_size > 0
    if checks["log_exists"]:
        evidence.append(str(lp)); reasons.append(f"Worker log exists ({lp.stat().st_size} bytes)")
    else:
        reasons.append("Worker log missing or empty")

    # 3: required files
    if config.required_files:
        af = all((root / p).exists() for p in config.required_files)
        checks["required_files_exist"] = af
        reasons.append("All required files present" if af else "Required files missing")
        if af:
            evidence.extend(str(root / p) for p in config.required_files)
    else:
        checks["required_files_exist"] = True

    # 4: test command
    if config.test_command:
        try:
            tr = subprocess.run(config.test_command, shell=True, capture_output=True, text=True, timeout=120, cwd=str(root))
            checks["test_command_ok"] = tr.returncode == 0
            reasons.append("Test command passed" if tr.returncode == 0 else f"Test command failed (exit {tr.returncode})")
            tl = lp.parent / "test_output.txt"; tl.write_text(f"STDOUT:\n{tr.stdout}\n\nSTDERR:\n{tr.stderr}", encoding="utf-8"); evidence.append(str(tl))
        except subprocess.TimeoutExpired:
            checks["test_command_ok"] = False; reasons.append("Test timed out")
        except FileNotFoundError:
            checks["test_command_ok"] = False; reasons.append("Test command not found")
    else:
        checks["test_command_ok"] = True

    # 5: metrics
    if config.metrics_file:
        mp = root / config.metrics_file
        checks["metrics_file_exists"] = mp.exists()
        if mp.exists():
            try:
                d = json.loads(mp.read_text(encoding="utf-8"))
                checks["metrics_file_valid"] = isinstance(d, dict)
                reasons.append("Metrics valid" if isinstance(d, dict) else "Metrics not object")
                evidence.append(str(mp))
            except json.JSONDecodeError:
                checks["metrics_file_valid"] = False; reasons.append("Metrics invalid JSON")
        else:
            checks["metrics_file_exists"] = False; checks["metrics_file_valid"] = False; reasons.append("Metrics file not found")
    else:
        checks["metrics_file_exists"] = True; checks["metrics_file_valid"] = True

    # ── Layer B ──────────────────────────────────────────────────────────

    # 6: git head saved
    if git_head_before:
        checks["git_head_saved"] = bool(git_head_before.strip())
        reasons.append(f"Git HEAD: {git_head_before[:12]}" if git_head_before.strip() else "HEAD not saved")
        if git_head_before.strip():
            evidence.append(f"HEAD={git_head_before[:12]}")
    else:
        checks["git_head_saved"] = True

    # 7: git working-tree discipline
    porcelain_lines: list[str] = []
    if config.check_git_clean or config.git_denied_paths:
        porcelain_lines = _run_git_porcelain(root)

    if config.check_git_clean:
        dp = _run_git_diff(root)
        checks["git_no_tracked_mods"] = not bool(dp.strip())
        reasons.append("No tracked files modified" if checks["git_no_tracked_mods"] else f"Tracked files modified:\n{dp[:1024]}")
        if porcelain_lines and config.git_allowed_prefixes:
            viol = _check_allowed_prefixes(porcelain_lines, config.git_allowed_prefixes)
            checks["git_changes_in_allowed_paths"] = len(viol) == 0
            reasons.append("All changes in allowed paths" if len(viol)==0 else f"Changes outside allowed paths:\n"+"\n".join(viol[:10]))
        else:
            checks["git_changes_in_allowed_paths"] = True
    else:
        checks["git_no_tracked_mods"] = True; checks["git_changes_in_allowed_paths"] = True

    # 8: git denied paths — authority file protection
    if config.git_denied_paths:
        viol = _check_denied_paths(porcelain_lines, config.git_denied_paths)
        checks["git_no_denied_touches"] = len(viol) == 0
        if checks["git_no_denied_touches"]:
            reasons.append("No authority files touched")
        else:
            reasons.append(f"Authority files modified — denied paths violated:\n" + "\n".join(viol[:5]))
    else:
        checks["git_no_denied_touches"] = True

    # ── Layer C ──────────────────────────────────────────────────────────

    # 9: required report fields in worker summary
    if config.check_report_fields and config.report_required_fields:
        found = []
        missing = []
        for field in config.report_required_fields:
            # Search in a case-insensitive manner
            pattern = re.compile(re.escape(field), re.IGNORECASE)
            if pattern.search(worker_summary):
                found.append(field)
            else:
                missing.append(field)
        checks["report_fields_ok"] = len(missing) == 0
        if checks["report_fields_ok"]:
            reasons.append(f"Report contains required fields: {', '.join(found)}")
        else:
            reasons.append(f"Report missing required fields: {', '.join(missing)}")
    else:
        checks["report_fields_ok"] = True

    # 10: synthetic signal test passfile
    if config.synthetic_test_passfile:
        sp = root / config.synthetic_test_passfile
        checks["synthetic_test_passed"] = sp.exists()
        if checks["synthetic_test_passed"]:
            reasons.append(f"Synthetic signal test passed ({sp})")
            evidence.append(str(sp))
        else:
            reasons.append(f"Synthetic signal test passfile not found: {config.synthetic_test_passfile}")
    else:
        checks["synthetic_test_passed"] = True

    # ── Verdict ──────────────────────────────────────────────────────────

    verdict = "PASS" if all(checks.values()) else "FAIL"
    return GateResult(verdict=verdict, check_results=checks, reasons=reasons, evidence_paths=evidence)


# ── git helpers ──────────────────────────────────────────────────────────

def _run_git_diff(r: Path) -> str:
    try:
        p = subprocess.run(["git","diff","--stat"], capture_output=True, text=True, timeout=15, cwd=str(r))
        return p.stdout.strip() if p.returncode == 0 else ""
    except: return ""

def _run_git_porcelain(r: Path) -> list[str]:
    try:
        p = subprocess.run(["git","status","--porcelain"], capture_output=True, text=True, timeout=15, cwd=str(r))
        return [l.strip() for l in p.stdout.strip().splitlines() if l.strip()] if p.returncode == 0 else []
    except: return []

def _check_allowed_prefixes(lines: list[str], prefixes: list[str]) -> list[str]:
    viol = []
    for l in lines:
        if len(l) < 4: continue
        path = l[3:].strip()
        if not any(path.startswith(p) for p in prefixes):
            viol.append(l)
    return viol

def _check_denied_paths(lines: list[str], denied: list[str]) -> list[str]:
    """Return porcelain lines that touch any denied path prefix."""
    viol = []
    for l in lines:
        if len(l) < 4: continue
        path = l[3:].strip()
        if any(path.startswith(p) for p in denied):
            viol.append(l)
    return viol
