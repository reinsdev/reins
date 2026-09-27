@echo off
rem reinsdev launcher (Windows cmd / PowerShell).
setlocal
set "ENTRY=%~dp0reinsdev.py"
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)" >nul 2>nul
if not errorlevel 1 goto use_py
python -c "import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)" >nul 2>nul
if not errorlevel 1 goto use_python
python3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)" >nul 2>nul
if not errorlevel 1 goto use_python3
echo reinsdev: Python 3.8+ not found 1>&2
exit /b 1
:use_py
py -3 "%ENTRY%" %*
exit /b %errorlevel%
:use_python
python "%ENTRY%" %*
exit /b %errorlevel%
:use_python3
python3 "%ENTRY%" %*
exit /b %errorlevel%
