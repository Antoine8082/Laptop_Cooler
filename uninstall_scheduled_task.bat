@echo off
:: ============================================================================
::  uninstall_scheduled_task.bat — Supprime la tâche planifiée Laptop Cooler
:: ============================================================================

echo.
echo ============================================================
echo   Laptop Cooler — Suppression de la tâche planifiée
echo ============================================================
echo.

net session >nul 2>&1
if %errorLevel% neq 0 (
    echo [ERREUR] Ce script doit être exécuté en tant qu'Administrateur !
    pause
    exit /b 1
)

set "TASK_NAME=LaptopCoolerAutoStart"

schtasks /Query /TN "%TASK_NAME%" >nul 2>&1
if %errorLevel% equ 0 (
    schtasks /Delete /TN "%TASK_NAME%" /F
    echo [OK] Tâche "%TASK_NAME%" supprimée.
) else (
    echo [INFO] La tâche "%TASK_NAME%" n'existe pas.
)

echo.
pause
