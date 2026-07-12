@echo off
REM V7 Colab Training Runner — Windows native
REM Calls colab-cli's own Python 3.13 directly

set TOOL_PYTHON=C:\Users\dresden\AppData\Roaming\uv\tools\google-colab-cli\Scripts\python.exe
set FAKE_TERMIOS=import sys,types;t=types.ModuleType('termios');t.TCSAFLUSH=2;t.TCSANOW=0;t.NCCS=20;sys.modules['termios']=t
set COLAB_CODE=%FAKE_TERMIOS%;from colab_cli.cli import app;app()

if "%1"=="" (
    %TOOL_PYTHON% -I -c "%COLAB_CODE%" --help
    goto :eof
)

%TOOL_PYTHON% -I -c "%COLAB_CODE%" %*
