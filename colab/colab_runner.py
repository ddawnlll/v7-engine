"""
V7 Colab Runner — Google Colab GPU training from Windows
Uses colab_cli Python library directly (Python 3.13 required)

Usage:
    python colab/colab_runner.py auth           # First-time auth
    python colab/colab_runner.py train --mode SCALP --symbols 5
    python colab/colab_runner.py status
    python colab/colab_runner.py stop
"""

import sys, os, json, time, base64, textwrap, types
from pathlib import Path

# ── Bootstrap: colab-cli requires Python >= 3.12 ──────────────────────────
# If running under hermes Python 3.11, re-exec with tool's own Python 3.13
TOOL_PYTHON = r"C:\Users\dresden\AppData\Roaming\uv\tools\google-colab-cli\Scripts\python.exe"

if sys.version_info < (3, 12) and os.path.exists(TOOL_PYTHON):
    os.execv(TOOL_PYTHON, [TOOL_PYTHON] + sys.argv)

# ── Termios dummy (Windows) ───────────────────────────────────────────────
t = types.ModuleType("termios")
t.TCSAFLUSH, t.TCSANOW, t.NCCS = 2, 0, 20
sys.modules["termios"] = t

# ── Imports ───────────────────────────────────────────────────────────────
from colab_cli.client import Client
from colab_cli.commands.session import handle_new
from colab_cli.commands.execution import handle_exec
from colab_cli.commands.run import handle_run

# ── Config ────────────────────────────────────────────────────────────────
SESSION_NAME = "v7-training"
NOTEBOOK_PATH = str(Path(__file__).parent / "v7_training_colab.ipynb")

def cmd_auth():
    """First-time Google OAuth"""
    from colab_cli.auth import ColabAuth
    auth = ColabAuth()
    creds = auth.authenticate()
    print("✅ Auth OK:", creds.token[:20] if hasattr(creds, 'token') else "token saved")

def cmd_train(mode="SCALP", symbols=5, folds=6, bars=3000):
    """Run V7 training on Colab GPU"""
    print(f"🚀 Starting V7 training: {mode} | {symbols} symbols | {folds} folds")

    # Execute the notebook on Colab
    params = f"MODE='{mode}'\nSYMBOLS_COUNT={symbols}\nFOLDS={folds}\nN_BARS={bars}\n"
    
    code = f"""
import os, json
os.chdir('/content')

# V7 training code (embedded or cloned)
%cd /content

# Install deps
!pip install -q numpy pandas scipy scikit-learn xgboost pyarrow matplotlib seaborn tqdm numba requests

# Clone repo
!git clone https://github.com/ddawnlll/alphaforge-infa.git /content/v7-engine 2>/dev/null || echo "already cloned"
%cd /content/v7-engine

# Run training
!python -m alphaforge.train --mode {mode} --synthetic --folds {folds} --features all
"""
    result = handle_run(
        name=SESSION_NAME,
        gpu="T4",
        script_content=code,
        output_dir="/content/drive/MyDrive/alphaforge_results",
    )
    print(f"✅ Training complete. Output: {result}")

def cmd_status():
    """Check session status"""
    client = Client()
    sessions = client.list_assignments()
    if not sessions:
        print("❌ No active sessions")
        return
    for s in sessions:
        print(f"  {s.get('name','?')}: {s.get('status','?')} GPU={s.get('gpu_type','?')}")

def cmd_stop():
    """Stop training session"""
    client = Client()
    sessions = client.list_assignments()
    for s in sessions:
        if SESSION_NAME in str(s.get("name", "")):
            client.unassign(s["name"])
            print(f"✅ Stopped: {s['name']}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]
    kwargs = {}
    for i in range(2, len(sys.argv)):
        if sys.argv[i].startswith("--"):
            key = sys.argv[i][2:]
            val = sys.argv[i+1] if i+1 < len(sys.argv) and not sys.argv[i+1].startswith("--") else True
            kwargs[key] = val

    cmds = {
        "auth": cmd_auth,
        "train": lambda: cmd_train(**kwargs),
        "status": cmd_status,
        "stop": cmd_stop,
    }
    fn = cmds.get(cmd)
    if fn:
        fn()
    else:
        print(f"Unknown command: {cmd}")
        print("Available: auth, train, status, stop")
