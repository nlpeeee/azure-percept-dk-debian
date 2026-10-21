@echo off
rem SPDX-License-Identifier: MIT
rem Windows launcher: finds a Python 3 and runs the percept script next to this file.
where py >nul 2>nul && (py -3 "%~dp0percept" %* & exit /b %errorlevel%)
where python >nul 2>nul && (python "%~dp0percept" %* & exit /b %errorlevel%)
echo Python 3 was not found. Install it from https://www.python.org/downloads/ and retry.
exit /b 127
