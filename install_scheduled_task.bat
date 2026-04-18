@echo off
:: ============================================================================
::  install_scheduled_task.bat
:: ============================================================================
::  Installe une tâche planifiée Windows qui lance Laptop_Cooler.exe
::  à chaque ouverture de session avec les droits Administrateur,
::  SANS invite UAC à chaque fois.
::
::  USAGE :
::    1. Clic droit → "Exécuter en tant qu'administrateur"
::    2. C'est tout ! L'application se lancera automatiquement au prochain login.
::
::  Pour désinstaller : lancer uninstall_scheduled_task.bat
:: ============================================================================

echo.
echo ============================================================
echo   Laptop Cooler — Installation de la tâche planifiée
echo ============================================================
echo.

:: Vérifier les droits admin
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo [ERREUR] Ce script doit être exécuté en tant qu'Administrateur !
    echo           Clic droit → "Exécuter en tant qu'administrateur"
    pause
    exit /b 1
)

:: Chemin de l'exécutable (dans le même répertoire que ce script)
set "EXE_PATH=%~dp0Laptop_Cooler.exe"

if not exist "%EXE_PATH%" (
    echo [ERREUR] Laptop_Cooler.exe introuvable dans le répertoire courant.
    echo          Chemin attendu : %EXE_PATH%
    pause
    exit /b 1
)

:: Nom de la tâche
set "TASK_NAME=LaptopCoolerAutoStart"

:: Supprimer l'ancienne tâche si elle existe
schtasks /Query /TN "%TASK_NAME%" >nul 2>&1
if %errorLevel% equ 0 (
    echo [INFO] Suppression de l'ancienne tâche...
    schtasks /Delete /TN "%TASK_NAME%" /F >nul 2>&1
)

:: Créer la tâche planifiée
:: - ONLOGON : se lance à chaque ouverture de session
:: - /RL HIGHEST : exécution avec les privilèges les plus élevés (admin)
:: - /F : forcer la création
echo [INFO] Création de la tâche planifiée...
schtasks /Create /TN "%TASK_NAME%" /TR "\"%EXE_PATH%\"" /SC ONLOGON /RL HIGHEST /F

if %errorLevel% equ 0 (
    echo.
    echo [OK] Tâche planifiée "%TASK_NAME%" créée avec succès !
    echo.
    echo      L'application démarrera automatiquement au prochain login,
    echo      avec les droits administrateur, SANS invite UAC.
    echo.
    echo      Pour lancer maintenant : double-cliquez sur Laptop_Cooler.exe
) else (
    echo.
    echo [ERREUR] Impossible de créer la tâche planifiée.
    echo          Vérifiez que vous avez les droits administrateur.
)

echo.
pause
