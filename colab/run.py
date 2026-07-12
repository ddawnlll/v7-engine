"""Colab CLI runner for Windows.
Usage: python run.py [args...]  or  python run.py run --gpu T4 script.py
"""
import sys, os, subprocess

TOOL_PY = r"C:\Users\dresden\AppData\Roaming\uv\tools\google-colab-cli\Scripts\python.exe"
FAKE = "import sys,types;t=types.ModuleType('termios');t.TCSAFLUSH=2;t.TCSANOW=0;t.NCCS=20;sys.modules['termios']=t"

args = sys.argv[1:] if len(sys.argv) > 1 else []
code = f"{FAKE};import sys;sys.argv=['colab']+{args};from colab_cli.cli import app;app()"

env = os.environ.copy()
for k in ["PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV"]:
    env.pop(k, None)

sys.exit(subprocess.call([TOOL_PY, "-I", "-c", code], env=env))
