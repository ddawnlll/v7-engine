"""Colab CLI — Windows native. v2 (stdin passthrough)
Usage: python colab/colab.py <args>...
"""
import subprocess, sys, os, json

TOOL_PY = r"C:\Users\dresden\AppData\Roaming\uv\tools\google-colab-cli\Scripts\python.exe"
FAKE = ("import sys,types;t=types.ModuleType('termios');"
        "t.TCSAFLUSH=2;t.TCSANOW=0;t.NCCS=20;sys.modules['termios']=t")

args_list = json.dumps(sys.argv[1:])
code = f"{FAKE};import sys;sys.argv=['colab']+{args_list};from colab_cli.cli import app;app()"

env = os.environ.copy()
for k in ["PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV"]:
    env.pop(k, None)

# stdin/stdout/stderr passthrough
sys.exit(subprocess.call([TOOL_PY, "-I", "-c", code], env=env))
