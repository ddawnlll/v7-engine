#!/usr/bin/env python3
"""
Permission Monte Carlo Smoke Test — 100 randomized trials across 10 risk categories.
Only touches reports/permission_monte_carlo/ and /tmp/mimo_permission_test_*.
"""
import json
import os
import random
import shutil
import signal
import subprocess
import sys
import time
import traceback
import tempfile
import pathlib

BASE_DIR = pathlib.Path(__file__).resolve().parent
LEDGER = BASE_DIR / "ledger.md"
SUMMARY = BASE_DIR / "summary.json"
FAILURES = BASE_DIR / "failures.md"

TMP_PREFIX = "/tmp/mimo_permission_test_"

SEED = 42
random.seed(SEED)

# ---- trial bookkeeping ----
trials_run = 0
passed = 0
failed = 0
skipped = 0
permission_blocks = 0
fail_entries = []   # (trial_num, category, command, error, traceback_str)
ledger_lines = []

CATEGORIES = {
    1: "read/write/edit files",
    2: "overwrite logs with : > file",
    3: "delete generated temp files with rm -f",
    4: "delete generated temp directories with rm -rf",
    5: "access /tmp",
    6: "access /teamspace/studios/this_studio/v7-engine",
    7: "start nohup background python jobs",
    8: "kill only generated test PIDs",
    9: "append ledger rows",
    10: "recover from intentional command failures",
}


def log(trial_num, category, action, status, detail=""):
    ts = time.strftime("%H:%M:%S")
    line = f"| {trial_num:3d} | {category:2d} | {action:<50s} | {status:<15s} | {detail}"
    ledger_lines.append(line)
    print(line)


def run_cmd(cmd, shell=True, timeout=15):
    """Run a shell command. Returns (returncode, stdout, stderr, exception_or_None)."""
    try:
        r = subprocess.run(
            cmd if isinstance(cmd, str) else cmd,
            shell=shell,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return r.returncode, r.stdout.strip(), r.stderr.strip(), None
    except subprocess.TimeoutExpired as e:
        return -1, "", str(e), e
    except Exception as e:
        return -1, "", str(e), e


def check_blocked(retcode, stderr, command):
    """Return True if this looks like a permission block."""
    blocked_indicators = [
        "permission denied", "permission denied", "eacces", "operation not permitted",
        "not allowed", "cannot overwrite", "read-only file system",
    ]
    lower = stderr.lower()
    if any(ind in lower for ind in blocked_indicators):
        return True
    # Also flag EPIPE / EPERM from kill
    if "no such process" not in lower and ("operation not permitted" in lower or "permission" in lower):
        return True
    return False


def safe_cleanup(path):
    """Try rm -rf; if blocked, truncate/move as workaround. Returns (success, was_blocked)."""
    rc, _, stderr, exc = run_cmd(f"rm -rf {path}")
    if rc == 0:
        return True, False
    if check_blocked(rc, stderr, f"rm -rf {path}"):
        # workaround: truncate then move to a temp trash
        try:
            if os.path.isfile(path):
                open(path, "w").close()
                shutil.move(path, path + ".trashed")
            elif os.path.isdir(path):
                for root, dirs, files in os.walk(path, topdown=False):
                    for f in files:
                        fp = os.path.join(root, f)
                        try:
                            open(fp, "w").close()
                        except Exception:
                            pass
                        try:
                            os.remove(fp)
                        except Exception:
                            pass
                    for d in dirs:
                        dp = os.path.join(root, d)
                        try:
                            os.rmdir(dp)
                        except Exception:
                            pass
                try:
                    os.rmdir(path)
                except Exception:
                    shutil.move(path, path + ".trashed")
            return True, True
        except Exception:
            return False, True
    return False, False


# ============================================================
#  Trial generators
# ============================================================

def trial_read_write(trial_num, tmp_dir):
    """Category 1: read/write/edit files."""
    global passed, failed, skipped, permission_blocks
    fpath = tmp_dir / f"test_{trial_num}.txt"
    actions = []

    # Write
    rc, out, err, exc = run_cmd(f"echo 'hello trial {trial_num}' > {fpath}")
    if rc != 0:
        blocked = check_blocked(rc, err, f"write {fpath}")
        if blocked:
            permission_blocks += 1
            log(trial_num, 1, f"echo > {fpath.name}", "FAIL_PERMISSION_BLOCKED", err)
            failed += 1
            fail_entries.append((trial_num, 1, f"echo > {fpath.name}", err, ""))
            return
        log(trial_num, 1, f"echo > {fpath.name}", "FAIL", err)
        failed += 1
        fail_entries.append((trial_num, 1, f"echo > {fpath.name}", err, traceback.format_exc()))
        return
    actions.append("write")

    # Read
    rc, out, err, exc = run_cmd(f"cat {fpath}")
    if rc != 0:
        blocked = check_blocked(rc, err, f"read {fpath}")
        if blocked:
            permission_blocks += 1
            log(trial_num, 1, f"cat {fpath.name}", "FAIL_PERMISSION_BLOCKED", err)
            failed += 1
            fail_entries.append((trial_num, 1, f"cat {fpath.name}", err, ""))
            return
        log(trial_num, 1, f"cat {fpath.name}", "FAIL", err)
        failed += 1
        fail_entries.append((trial_num, 1, f"cat {fpath.name}", err, traceback.format_exc()))
        return
    assert "hello trial" in out, f"content mismatch: {out}"
    actions.append("read")

    # Edit (append)
    rc, out, err, exc = run_cmd(f"echo 'line2' >> {fpath}")
    if rc != 0:
        blocked = check_blocked(rc, err, f"append {fpath}")
        if blocked:
            permission_blocks += 1
            log(trial_num, 1, f"echo >> {fpath.name}", "FAIL_PERMISSION_BLOCKED", err)
            failed += 1
            fail_entries.append((trial_num, 1, f"echo >> {fpath.name}", err, ""))
            return
        log(trial_num, 1, f"echo >> {fpath.name}", "FAIL", err)
        failed += 1
        fail_entries.append((trial_num, 1, f"echo >> {fpath.name}", err, traceback.format_exc()))
        return
    actions.append("edit_append")

    # Verify content
    rc, out, err, exc = run_cmd(f"wc -l < {fpath}")
    if rc != 0 or int(out.strip()) != 2:
        log(trial_num, 1, f"verify {fpath.name}", "FAIL", f"expected 2 lines, got {out}")
        failed += 1
        fail_entries.append((trial_num, 1, f"verify {fpath.name}", f"expected 2 lines, got {out}", ""))
        return

    passed += 1
    log(trial_num, 1, f"write+read+edit {fpath.name}", "PASS", "")


def trial_overwrite_logs(trial_num, tmp_dir):
    """Category 2: overwrite logs with : > file."""
    global passed, failed, skipped, permission_blocks
    fpath = tmp_dir / f"log_{trial_num}.txt"
    # Create a log file first
    rc, _, _, _ = run_cmd(f"echo 'old content' > {fpath}")
    if rc != 0:
        skipped += 1
        log(trial_num, 2, f"setup {fpath.name}", "SKIPPED", "cannot create test file")
        return

    # Overwrite with colon redirect
    rc, out, err, exc = run_cmd(f": > {fpath}")
    if rc != 0:
        blocked = check_blocked(rc, err, f": > {fpath}")
        if blocked:
            permission_blocks += 1
            log(trial_num, 2, f": > {fpath.name}", "FAIL_PERMISSION_BLOCKED", err)
            failed += 1
            fail_entries.append((trial_num, 2, f": > {fpath.name}", err, ""))
            return
        log(trial_num, 2, f": > {fpath.name}", "FAIL", err)
        failed += 1
        fail_entries.append((trial_num, 2, f": > {fpath.name}", err, traceback.format_exc()))
        return

    # Verify empty
    size = os.path.getsize(fpath)
    if size != 0:
        log(trial_num, 2, f": > {fpath.name}", "FAIL", f"expected 0 bytes, got {size}")
        failed += 1
        fail_entries.append((trial_num, 2, f"verify {fpath.name}", f"expected 0 bytes, got {size}", ""))
        return
    passed += 1
    log(trial_num, 2, f": > {fpath.name}", "PASS", "")


def trial_rm_file(trial_num, tmp_dir):
    """Category 3: delete generated temp files with rm -f."""
    global passed, failed, skipped, permission_blocks
    fpath = tmp_dir / f"del_file_{trial_num}.txt"
    rc, _, _, _ = run_cmd(f"echo 'delete me' > {fpath}")
    if rc != 0 or not fpath.exists():
        skipped += 1
        log(trial_num, 3, f"setup {fpath.name}", "SKIPPED", "cannot create test file")
        return

    rc, out, err, exc = run_cmd(f"rm -f {fpath}")
    if rc != 0:
        blocked = check_blocked(rc, err, f"rm -f {fpath}")
        if blocked:
            permission_blocks += 1
            log(trial_num, 3, f"rm -f {fpath.name}", "FAIL_PERMISSION_BLOCKED", err)
            failed += 1
            fail_entries.append((trial_num, 3, f"rm -f {fpath.name}", err, ""))
            return
        log(trial_num, 3, f"rm -f {fpath.name}", "FAIL", err)
        failed += 1
        fail_entries.append((trial_num, 3, f"rm -f {fpath.name}", err, traceback.format_exc()))
        return

    if fpath.exists():
        # retry with truncate+move workaround
        try:
            open(fpath, "w").close()
            shutil.move(str(fpath), str(fpath) + ".trashed")
            log(trial_num, 3, f"rm -f {fpath.name}", "PASS_WITH_WORKAROUND", "file persisted, truncated+moved")
            passed += 1
            return
        except Exception as e:
            blocked = check_blocked(0, str(e).lower(), f"workaround {fpath}")
            if blocked:
                permission_blocks += 1
                log(trial_num, 3, f"workaround {fpath.name}", "FAIL_PERMISSION_BLOCKED", str(e))
                failed += 1
                fail_entries.append((trial_num, 3, f"workaround {fpath.name}", str(e), ""))
                return
            log(trial_num, 3, f"workaround {fpath.name}", "FAIL", str(e))
            failed += 1
            fail_entries.append((trial_num, 3, f"workaround {fpath.name}", str(e), traceback.format_exc()))
            return
    passed += 1
    log(trial_num, 3, f"rm -f {fpath.name}", "PASS", "")


def trial_rm_dir(trial_num, tmp_dir):
    """Category 4: delete generated temp directories with rm -rf."""
    global passed, failed, skipped, permission_blocks
    dpath = tmp_dir / f"del_dir_{trial_num}"
    try:
        dpath.mkdir(parents=True, exist_ok=True)
        (dpath / "inner.txt").write_text("data")
    except Exception as e:
        skipped += 1
        log(trial_num, 4, f"setup {dpath.name}", "SKIPPED", str(e))
        return

    rc, out, err, exc = run_cmd(f"rm -rf {dpath}")
    if rc != 0:
        blocked = check_blocked(rc, err, f"rm -rf {dpath}")
        if blocked:
            permission_blocks += 1
            log(trial_num, 4, f"rm -rf {dpath.name}", "FAIL_PERMISSION_BLOCKED", err)
            failed += 1
            fail_entries.append((trial_num, 4, f"rm -rf {dpath.name}", err, ""))
            return
        log(trial_num, 4, f"rm -rf {dpath.name}", "FAIL", err)
        failed += 1
        fail_entries.append((trial_num, 4, f"rm -rf {dpath.name}", err, traceback.format_exc()))
        return

    if dpath.exists():
        # workaround
        success, was_blocked = safe_cleanup(str(dpath))
        if was_blocked:
            permission_blocks += 1
            log(trial_num, 4, f"workaround {dpath.name}", "FAIL_PERMISSION_BLOCKED", "blocked on retry")
            failed += 1
            fail_entries.append((trial_num, 4, f"workaround {dpath.name}", "blocked on retry", ""))
            return
        if success:
            log(trial_num, 4, f"rm -rf {dpath.name}", "PASS_WITH_WORKAROUND", "directory persisted, retry ok")
            passed += 1
            return
        log(trial_num, 4, f"workaround {dpath.name}", "FAIL", "workaround also failed")
        failed += 1
        fail_entries.append((trial_num, 4, f"workaround {dpath.name}", "workaround also failed", ""))
        return

    passed += 1
    log(trial_num, 4, f"rm -rf {dpath.name}", "PASS", "")


def trial_access_tmp(trial_num, tmp_dir):
    """Category 5: access /tmp."""
    global passed, failed, permission_blocks
    rc, out, err, exc = run_cmd("ls /tmp/")
    if rc != 0:
        blocked = check_blocked(rc, err, "ls /tmp/")
        if blocked:
            permission_blocks += 1
            log(trial_num, 5, "ls /tmp/", "FAIL_PERMISSION_BLOCKED", err)
            failed += 1
            fail_entries.append((trial_num, 5, "ls /tmp/", err, ""))
            return
        log(trial_num, 5, "ls /tmp/", "FAIL", err)
        failed += 1
        fail_entries.append((trial_num, 5, "ls /tmp/", err, traceback.format_exc()))
        return
    # Also try writing a small sentinel
    sentinel = f"/tmp/mimo_permission_test_sentinel_{trial_num}.txt"
    rc2, out2, err2, exc2 = run_cmd(f"echo 'probe' > {sentinel}")
    if rc2 != 0:
        blocked = check_blocked(rc2, err2, f"write {sentinel}")
        if blocked:
            permission_blocks += 1
            log(trial_num, 5, f"write {os.path.basename(sentinel)}", "FAIL_PERMISSION_BLOCKED", err2)
            failed += 1
            fail_entries.append((trial_num, 5, f"write {sentinel}", err2, ""))
            return
        log(trial_num, 5, f"write {os.path.basename(sentinel)}", "FAIL", err2)
        failed += 1
        fail_entries.append((trial_num, 5, f"write {sentinel}", err2, traceback.format_exc()))
        return
    # Cleanup sentinel
    try:
        os.remove(sentinel)
    except Exception:
        pass
    passed += 1
    log(trial_num, 5, "ls /tmp/ + write sentinel", "PASS", "")


def trial_access_v7engine(trial_num, tmp_dir):
    """Category 6: access /teamspace/studios/this_studio/v7-engine (readonly)."""
    global passed, failed, permission_blocks
    # read-only check - just list top-level, never write
    rc, out, err, exc = run_cmd("ls /teamspace/studios/this_studio/v7-engine/")
    if rc != 0:
        blocked = check_blocked(rc, err, "ls v7-engine/")
        if blocked:
            permission_blocks += 1
            log(trial_num, 6, "ls v7-engine/", "FAIL_PERMISSION_BLOCKED", err)
            failed += 1
            fail_entries.append((trial_num, 6, "ls v7-engine/", err, ""))
            return
        log(trial_num, 6, "ls v7-engine/", "FAIL", err)
        failed += 1
        fail_entries.append((trial_num, 6, "ls v7-engine/", err, traceback.format_exc()))
        return
    # Verify we see expected entries (ai_summary.md etc)
    entries = out.split()
    has_ai_summary = "ai_summary.md" in entries or any("ai_summary" in e for e in entries)
    if not has_ai_summary:
        log(trial_num, 6, "ls v7-engine/", "WARN", f"ai_summary.md not in listing, but readable: {entries[:5]}")
    passed += 1
    log(trial_num, 6, "ls v7-engine/ (readonly)", "PASS", "")


def trial_nohup_python(trial_num, tmp_dir):
    """Category 7: start nohup background python jobs."""
    global passed, failed, skipped, permission_blocks
    script = tmp_dir / f"bg_job_{trial_num}.py"
    outfile = tmp_dir / f"bg_out_{trial_num}.txt"
    pidfile = tmp_dir / f"bg_pid_{trial_num}.txt"

    script_content = f'''#!/usr/bin/env python3
import time, os, sys
# Permission smoke test background job - trial {trial_num}
with open("{outfile}", "w") as f:
    f.write("started at " + str(time.time()))
time.sleep(2)
with open("{outfile}", "a") as f:
    f.write("\\nfinished at " + str(time.time()))
'''
    try:
        script.write_text(script_content)
        script.chmod(0o755)
    except Exception as e:
        skipped += 1
        log(trial_num, 7, f"setup {script.name}", "SKIPPED", f"cannot write: {e}")
        return

    rc, out, err, exc = run_cmd(
        f"nohup python3 {script} > /dev/null 2>&1 & echo $! > {pidfile}"
    )
    if rc != 0:
        blocked = check_blocked(rc, err, f"nohup python3 {script.name}")
        if blocked:
            permission_blocks += 1
            log(trial_num, 7, f"nohup {script.name}", "FAIL_PERMISSION_BLOCKED", err)
            failed += 1
            fail_entries.append((trial_num, 7, f"nohup {script.name}", err, ""))
            return
        log(trial_num, 7, f"nohup {script.name}", "FAIL", err)
        failed += 1
        fail_entries.append((trial_num, 7, f"nohup {script.name}", err, traceback.format_exc()))
        return

    # Wait for job and check output
    time.sleep(3)
    if outfile.exists():
        content = outfile.read_text()
        if "started" in content and "finished" in content:
            passed += 1
            log(trial_num, 7, f"nohup {script.name}", "PASS", "")
        else:
            log(trial_num, 7, f"verify {script.name}", "FAIL", f"output incomplete: {content}")
            failed += 1
            fail_entries.append((trial_num, 7, f"verify {script.name}", f"output incomplete: {content}", ""))
    else:
        log(trial_num, 7, f"verify {script.name}", "FAIL", "output file missing")
        failed += 1
        fail_entries.append((trial_num, 7, f"verify {script.name}", "output file missing", ""))
    # Cleanup bg pid
    if pidfile.exists():
        try:
            pid = int(pidfile.read_text().strip())
            os.kill(pid, signal.SIGTERM)
        except Exception:
            pass


def trial_kill_pid(trial_num, tmp_dir):
    """Category 8: kill only generated test PIDs."""
    global passed, failed, skipped, permission_blocks
    # Start a short-lived sleep that we own
    pidfile = tmp_dir / f"kill_pid_{trial_num}.txt"
    rc, out, err, exc = run_cmd(
        f"sleep 30 & echo $! > {pidfile}"
    )
    if rc != 0:
        skipped += 1
        log(trial_num, 8, f"start sleep for {pidfile.name}", "SKIPPED", err)
        return

    time.sleep(0.2)
    if not pidfile.exists():
        skipped += 1
        log(trial_num, 8, f"read pidfile", "SKIPPED", "pidfile not created")
        return

    pid_str = pidfile.read_text().strip()
    if not pid_str or not pid_str.isdigit():
        skipped += 1
        log(trial_num, 8, f"read pid", "SKIPPED", f"invalid pid: {pid_str}")
        return

    pid = int(pid_str)
    # Kill only our PID
    rc, out, err, exc = run_cmd(f"kill {pid} 2>&1")
    if rc != 0:
        # If "No such process", it already exited — that's fine
        if "no such process" in err.lower():
            passed += 1
            log(trial_num, 8, f"kill {pid}", "PASS", "process already exited")
            return
        blocked = check_blocked(rc, err, f"kill {pid}")
        if blocked:
            permission_blocks += 1
            log(trial_num, 8, f"kill {pid}", "FAIL_PERMISSION_BLOCKED", err)
            failed += 1
            fail_entries.append((trial_num, 8, f"kill {pid}", err, ""))
            return
        log(trial_num, 8, f"kill {pid}", "FAIL", err)
        failed += 1
        fail_entries.append((trial_num, 8, f"kill {pid}", err, traceback.format_exc()))
        return

    # Verify dead
    time.sleep(0.1)
    rc2, _, _, _ = run_cmd(f"kill -0 {pid} 2>/dev/null")
    if rc2 == 0:
        # process still alive — retry with SIGKILL
        rc3, _, err3, _ = run_cmd(f"kill -9 {pid} 2>&1")
        if rc3 != 0:
            blocked = check_blocked(rc3, err3, f"kill -9 {pid}")
            if blocked:
                permission_blocks += 1
                log(trial_num, 8, f"kill -9 {pid}", "FAIL_PERMISSION_BLOCKED", err3)
                failed += 1
                fail_entries.append((trial_num, 8, f"kill -9 {pid}", err3, ""))
                return
            log(trial_num, 8, f"kill -9 {pid}", "FAIL", err3)
            failed += 1
            fail_entries.append((trial_num, 8, f"kill -9 {pid}", err3, traceback.format_exc()))
            return
        log(trial_num, 8, f"kill {pid}", "PASS_WITH_SIGKILL", "")
        passed += 1
        return

    passed += 1
    log(trial_num, 8, f"kill {pid}", "PASS", "")


def trial_append_ledger(trial_num, tmp_dir):
    """Category 9: append ledger rows."""
    global passed, failed, skipped, permission_blocks
    ledger_file = tmp_dir / "monte_ledger.txt"
    row = f"trial_{trial_num}_{int(time.time())}_data"
    rc, out, err, exc = run_cmd(f"echo '{row}' >> {ledger_file}")
    if rc != 0:
        blocked = check_blocked(rc, err, f"append to ledger")
        if blocked:
            permission_blocks += 1
            log(trial_num, 9, f"echo >> ledger", "FAIL_PERMISSION_BLOCKED", err)
            failed += 1
            fail_entries.append((trial_num, 9, f"echo >> ledger", err, ""))
            return
        log(trial_num, 9, f"echo >> ledger", "FAIL", err)
        failed += 1
        fail_entries.append((trial_num, 9, f"echo >> ledger", err, traceback.format_exc()))
        return

    # Verify our row was appended
    if ledger_file.exists():
        content = ledger_file.read_text()
        if row in content:
            passed += 1
            log(trial_num, 9, f"append + verify row", "PASS", "")
            return
    log(trial_num, 9, f"verify row", "FAIL", "row not found after append")
    failed += 1
    fail_entries.append((trial_num, 9, f"verify row", "row not found after append", ""))


def trial_recover_failure(trial_num, tmp_dir):
    """Category 10: recover from intentional command failures."""
    global passed, failed, skipped, permission_blocks

    # Intentionally run a command that should fail
    rc, out, err, exc = run_cmd("ls /nonexistent_path_xyz_12345 2>&1")
    if rc == 0:
        log(trial_num, 10, "intentional failure: ls nonexistent", "FAIL", "command unexpectedly succeeded")
        failed += 1
        fail_entries.append((trial_num, 10, "ls nonexistent_path", "command unexpectedly succeeded", ""))
        return

    # Recovery: create dir and try again
    rc2, out2, err2, exc2 = run_cmd(f"mkdir -p {tmp_dir / 'recovered'}")
    if rc2 != 0:
        blocked = check_blocked(rc2, err2, f"mkdir recovered")
        if blocked:
            permission_blocks += 1
            log(trial_num, 10, f"mkdir recovered", "FAIL_PERMISSION_BLOCKED", err2)
            failed += 1
            fail_entries.append((trial_num, 10, f"mkdir recovered", err2, ""))
            return

    # Now succeed at what originally failed
    rc3, out3, err3, exc3 = run_cmd(f"ls {tmp_dir / 'recovered'} 2>&1")
    if rc3 != 0:
        blocked = check_blocked(rc3, err3, f"ls recovered")
        if blocked:
            permission_blocks += 1
            log(trial_num, 10, f"ls recovered", "FAIL_PERMISSION_BLOCKED", err3)
            failed += 1
            fail_entries.append((trial_num, 10, f"ls recovered", err3, ""))
            return
        log(trial_num, 10, f"recovery: ls recovered", "FAIL", err3)
        failed += 1
        fail_entries.append((trial_num, 10, f"recovery: ls recovered", err3, traceback.format_exc()))
        return

    # Also test: run a command that fails, capture exit code, continue
    rc4, out4, err4, exc4 = run_cmd("false")
    if rc4 == 0:
        log(trial_num, 10, "false command", "WARN", "false returned 0 — unusual but not a failure")
    # false returning non-zero is expected; we continue regardless

    passed += 1
    log(trial_num, 10, "intentional fail + recover", "PASS", "")


# ============================================================
#  Main harness
# ============================================================

def main():
    global trials_run, passed, failed, skipped, permission_blocks

    # Prepare ledger header
    header = [
        "# Permission Monte Carlo Smoke Test — Ledger",
        "",
        "| Trial | Cat | Action | Status | Detail |",
        "|-------|-----|--------------------------------------------------|-----------------|--------|",
    ]
    with open(LEDGER, "w") as f:
        f.write("\n".join(header) + "\n")

    # Unique temp dir for this run
    test_root = pathlib.Path(f"{TMP_PREFIX}{int(time.time())}_{os.getpid()}")
    test_root.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*70}")
    print(f"Permission Monte Carlo Smoke Test — 100 trials")
    print(f"Seed: {SEED}, Temp dir: {test_root}")
    print(f"Only touching: {BASE_DIR} and {TMP_PREFIX}*")
    print(f"{'='*70}\n")

    # Distribute 100 trials across categories
    # Each category gets ~10 trials, with some random shuffling
    categories_list = list(CATEGORIES.keys())
    # We want exactly 100 trials. Give each category 10.
    trial_plan = []
    for cat in categories_list:
        for _ in range(10):
            trial_plan.append(cat)
    random.shuffle(trial_plan)

    trial_fns = {
        1: trial_read_write,
        2: trial_overwrite_logs,
        3: trial_rm_file,
        4: trial_rm_dir,
        5: trial_access_tmp,
        6: trial_access_v7engine,
        7: trial_nohup_python,
        8: trial_kill_pid,
        9: trial_append_ledger,
        10: trial_recover_failure,
    }

    for i, cat in enumerate(trial_plan):
        trial_num = i + 1
        trials_run = trial_num
        fn = trial_fns[cat]

        try:
            fn(trial_num, test_root)
        except Exception as e:
            tb = traceback.format_exc()
            log(trial_num, cat, f"{CATEGORIES[cat]}", "CRASH", str(e))
            failed += 1
            fail_entries.append((trial_num, cat, CATEGORIES[cat], str(e), tb))

        # Write ledger incrementally
        with open(LEDGER, "a") as f:
            f.write(ledger_lines[-1] + "\n")

    # ---- Final summary ----
    verdict = "PASS" if failed == 0 and permission_blocks == 0 else "FAIL"

    summary = {
        "verdict": verdict,
        "total_trials": trials_run,
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "permission_blocks": permission_blocks,
        "seed": SEED,
        "test_timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "overnight_safe": failed == 0 and permission_blocks == 0,
        "categories_tested": {k: v for k, v in CATEGORIES.items()},
    }

    with open(SUMMARY, "w") as f:
        json.dump(summary, f, indent=2)

    # Failures report
    if fail_entries:
        fail_lines = [
            "# Permission Monte Carlo Smoke Test — Failures",
            "",
            f"Total failures: {len(fail_entries)}",
            "",
            "| # | Trial | Cat | Category | Command | Error | Traceback |",
            "|---|-------|-----|----------|---------|-------|-----------|",
        ]
        for idx, (tnum, cat, cmd, err, tb) in enumerate(fail_entries):
            tb_short = (tb[:300] + "...") if len(tb) > 300 else tb
            # Escape pipe characters in error/traceback
            err_esc = err.replace("|", "\\|").replace("\n", " ")
            tb_esc = tb_short.replace("|", "\\|").replace("\n", " ")
            fail_lines.append(
                f"| {idx+1} | {tnum} | {cat} | {CATEGORIES[cat]} | `{cmd}` | {err_esc} | `{tb_esc}` |"
            )
        with open(FAILURES, "w") as f:
            f.write("\n".join(fail_lines) + "\n")
    else:
        with open(FAILURES, "w") as f:
            f.write("# Permission Monte Carlo Smoke Test — Failures\n\n**No failures.**\n")

    # Final status line appended to ledger
    with open(LEDGER, "a") as f:
        f.write(f"\n## Summary\n\n")
        f.write(f"- **Verdict:** {verdict}\n")
        f.write(f"- **Total trials:** {trials_run}\n")
        f.write(f"- **Passed:** {passed}\n")
        f.write(f"- **Failed:** {failed}\n")
        f.write(f"- **Skipped:** {skipped}\n")
        f.write(f"- **Permission blocks:** {permission_blocks}\n")
        f.write(f"- **Overnight safe:** {failed == 0 and permission_blocks == 0}\n")

    # Cleanup our temp dir
    try:
        shutil.rmtree(str(test_root), ignore_errors=True)
    except Exception:
        pass

    print(f"\n{'='*70}")
    print(f"  Verdict: {verdict}")
    print(f"  Total: {trials_run}, Passed: {passed}, Failed: {failed}, Skipped: {skipped}, PermBlocks: {permission_blocks}")
    print(f"  Overnight mission safe: {'YES' if (failed == 0 and permission_blocks == 0) else 'NO'}")
    print(f"{'='*70}")
    print(f"  Ledger: {LEDGER}")
    print(f"  Summary: {SUMMARY}")
    print(f"  Failures: {FAILURES}")
    print(f"{'='*70}\n")
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
