@echo off
REM Colab CLI for Windows (uses tool's Python 3.13)
REM Usage: colab auth | colab run --gpu T4 script.py | colab exec -f notebook.ipynb

set TOOL_PY=C:\Users\dresden\AppData\Roaming\uv\tools\google-colab-cli\Scripts\python.exe

if "%1"=="" (
    %TOOL_PY% -I -c "import sys,types;t=types.ModuleType('termios');t.TCSAFLUSH=2;t.TCSANOW=0;t.NCCS=20;sys.modules['termios']=t;from colab_cli.cli import app;app()"
    goto :eof
)

%TOOL_PY% -I -c "import sys,types;t=types.ModuleType('termios');t.TCSAFLUSH=2;t.TCSANOW=0;t.NCCS=20;sys.modules['termios']=t;sys.argv=['colab']+%*;from colab_cli.cli import app;app()"
