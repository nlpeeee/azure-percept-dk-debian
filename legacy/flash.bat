@echo off
REM ============================================================================
REM Azure Percept DK — Flash Debian Image (Windows)
REM
REM Usage:
REM   1. Request USB recovery with vendor flagutil + orderly reboot; see README.
REM      Without SSH, follow the board's documented internal DIP-switch procedure.
REM   2. Double-click this file or run from PowerShell
REM ============================================================================

echo.
echo  =========================================================
echo   Azure Percept DK — Debian Flash
echo  =========================================================
echo.

REM Check for UUU
where uuu.exe >nul 2>&1
if %errorlevel% neq 0 (
    if exist "%~dp0uuu.exe" (
        set "UUU=%~dp0uuu.exe"
    ) else (
        echo ERROR: uuu.exe not found in PATH or current directory.
        echo Download from: https://github.com/nxp-imx/mfgtools/releases
        pause
        exit /b 1
    )
) else (
    set "UUU=uuu.exe"
)

REM Check for flash image
if not exist "%~dp0output\debian-percept-dk.raw" (
    echo ERROR: output\debian-percept-dk.raw not found.
    echo Run 01_build_image.sh in WSL first.
    pause
    exit /b 1
)

echo Flashing device...
echo.
cd /d "%~dp0"
%UUU% flash.uuu

echo.
if %errorlevel% equ 0 (
    echo  =========================================================
    echo   Flash complete!
    echo  =========================================================
    echo.
    echo   1. Unplug USB cable
    echo   2. Power cycle the board
    echo   3. Wait 30-60 seconds
    echo   4. SSH to: root@192.168.1.100 
    echo   5. Run:    bash /root/post_flash.sh
    echo.
) else (
    echo  Flash FAILED. Check that device is in USB recovery mode.
)

pause
