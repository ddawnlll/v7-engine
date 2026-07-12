@echo off
setlocal enabledelayedexpansion

set TOOL_PY=C:\Users\dresden\AppData\Roaming\uv\tools\google-colab-cli\Scripts\python.exe

REM Build args as JSON array with single quotes for Python
set ARGS=
for %%a in (%*) do (
    if "!ARGS!"=="" (
        set ARGS='%%a'
    ) else (
        set ARGS=!ARGS!,'%%a'
    )
)

REM Code with single quotes for inner Python strings
set FAKE=import sys,types;t=types.ModuleType('termios');t.TCSAFLUSH=2;t.TCSANOW=0;t.NCCS=20;sys.modules['termios']=t
set CODE=%FAKE%;import sys;sys.argv=['colab']+[%ARGS%];from colab_cli.cli import app;app()

"%TOOL_PY%" -I -c "%CODE%"

endlocal
