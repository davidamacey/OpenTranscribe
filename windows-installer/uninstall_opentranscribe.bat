@echo off
REM ============================================================================
REM OpenTranscribe Windows Uninstaller
REM ============================================================================
REM
REM Purpose: Remove OpenTranscribe containers, images, and volumes from Windows
REM
REM This script performs the following:
REM 1. Stops and removes OpenTranscribe Docker containers
REM 2. Removes Docker volumes (database data, MinIO storage, etc.)
REM 3. Removes Docker images
REM 4. Optionally removes user data directories
REM
REM Usage: Double-click uninstall_opentranscribe.bat or run from command prompt
REM        Called automatically by Inno Setup uninstaller with /SILENT parameter
REM
REM Prerequisites:
REM - Docker Desktop must be running
REM ============================================================================

setlocal EnableDelayedExpansion

REM Check for silent mode parameter
set "SILENT_MODE=0"
if /i "%~1"=="/SILENT" set "SILENT_MODE=1"

if %SILENT_MODE% equ 0 (
    echo ========================================
    echo    OpenTranscribe Uninstallation
    echo ========================================
    echo.
    echo This will remove OpenTranscribe containers, images, and volumes.
    echo.
    echo WARNING: This will delete all transcription data, database contents,
    echo and MinIO storage. Make sure you have backed up any important data.
    echo.
    pause
)

REM Get the installation directory (where this script is located)
set "INSTALL_DIR=%~dp0"
cd /d "%INSTALL_DIR%"

REM Check if Docker Desktop is running
if %SILENT_MODE% equ 0 echo Checking Docker Desktop status...
docker info >nul 2>&1
if %errorlevel% neq 0 (
    if %SILENT_MODE% equ 0 (
        echo.
        echo WARNING: Docker Desktop is not running!
        echo Some cleanup operations may not complete.
        echo.
        echo Continue anyway? ^(y/N^)
        set /p "CONTINUE="
        if /i not "!CONTINUE!"=="y" (
            echo Uninstallation cancelled.
            pause
            exit /b 1
        )
    )
) else (
    if %SILENT_MODE% equ 0 echo Docker Desktop is running.
)

if %SILENT_MODE% equ 0 (
    echo.
    echo ========================================
    echo   Removing OpenTranscribe Services
    echo ========================================
    echo.
)

REM Prompt for removal options (only in interactive mode)
set "REMOVE_VOLUMES=n"
set "REMOVE_IMAGES=n"

if %SILENT_MODE% equ 0 (
    echo Do you want to remove Docker volumes ^(database data, MinIO storage, etc.^)?
    echo WARNING: This will delete all your transcriptions and data!
    echo.
    echo Remove volumes? ^(y/N^)
    set /p "REMOVE_VOLUMES="
    echo.

    echo Do you want to remove Docker images ^(~10-30GB^)?
    echo If removed, you'll need to re-load images from tar files on next install.
    echo.
    echo Remove images? ^(y/N^)
    set /p "REMOVE_IMAGES="
    echo.
) else (
    REM Silent mode: remove everything for complete cleanup
    set "REMOVE_VOLUMES=y"
    set "REMOVE_IMAGES=y"
)

REM Build docker compose down command with appropriate flags
set "COMPOSE_CMD=docker compose -f "%INSTALL_DIR%config\docker-compose.offline.yml" down --remove-orphans"

REM Add -v flag if removing volumes
if /i "!REMOVE_VOLUMES!"=="y" (
    set "COMPOSE_CMD=!COMPOSE_CMD! -v"
)

REM Add --rmi all flag if removing images
if /i "!REMOVE_IMAGES!"=="y" (
    set "COMPOSE_CMD=!COMPOSE_CMD! --rmi all"
)

REM Use docker compose down to remove resources
if exist "%INSTALL_DIR%config\docker-compose.offline.yml" (
    if %SILENT_MODE% equ 0 (
        echo Removing containers...
        if /i "!REMOVE_VOLUMES!"=="y" echo Removing volumes...
        if /i "!REMOVE_IMAGES!"=="y" echo Removing images...
        echo.
    )

    REM Execute the compose down command
    !COMPOSE_CMD!

    if %errorlevel% equ 0 (
        if %SILENT_MODE% equ 0 (
            echo.
            echo ✓ Containers removed
            if /i "!REMOVE_VOLUMES!"=="y" echo ✓ Volumes removed
            if /i "!REMOVE_IMAGES!"=="y" echo ✓ Images removed
            echo ✓ Networks removed
            echo.
        )
    ) else (
        if %SILENT_MODE% equ 0 (
            echo.
            echo WARNING: Some resources may not have been removed.
            echo Check that Docker Desktop is running and try again.
            echo.
        )
    )
) else (
    if %SILENT_MODE% equ 0 (
        echo WARNING: docker-compose.offline.yml not found.
        echo Cannot perform automatic cleanup.
        echo.
        echo You can manually clean up with:
        echo   docker ps -a    (view containers)
        echo   docker images   (view images)
        echo   docker volume ls (view volumes)
        echo.
    )
)

REM Prompt for data directory cleanup (only in interactive mode)
if %SILENT_MODE% equ 0 (
    echo.
    echo ========================================
    echo   Data Directory Cleanup
    echo ========================================
    echo.
    echo Do you want to remove the model cache and configuration files?
    echo This will free up 5-40GB of disk space depending on the model size.
    echo.
    echo WARNING: If you reinstall OpenTranscribe, models will need to be
    echo          re-downloaded or re-included in the installer.
    echo.
    echo Remove model cache? ^(y/N^)
    set /p "REMOVE_MODELS="

    if /i "!REMOVE_MODELS!"=="y" (
        if exist "%INSTALL_DIR%models" (
            echo Removing model cache...
            rmdir /s /q "%INSTALL_DIR%models" 2>nul
            echo Model cache removed.
        )
    ) else (
        echo Model cache preserved.
    )

    echo.
    echo Do you want to remove configuration files?
    echo ^(Includes .env and docker-compose configuration^)
    echo.
    echo Remove configuration? ^(y/N^)
    set /p "REMOVE_CONFIG="

    if /i "!REMOVE_CONFIG!"=="y" (
        if exist "%INSTALL_DIR%config" (
            echo Removing configuration files...
            rmdir /s /q "%INSTALL_DIR%config" 2>nul
            echo Configuration removed.
        )
        if exist "%INSTALL_DIR%.env" (
            del /q "%INSTALL_DIR%.env" 2>nul
        )
    ) else (
        echo Configuration preserved.
    )
)

REM Final cleanup
if %SILENT_MODE% equ 0 (
    echo.
    echo ========================================
    echo   Uninstallation Complete
    echo ========================================
    echo.
    echo OpenTranscribe has been uninstalled from your system.
    echo.
    echo Removed:
    echo   - Docker containers and networks
    if /i "!REMOVE_VOLUMES!"=="y" echo   - Docker volumes ^(database and storage data^)
    if /i "!REMOVE_IMAGES!"=="y" echo   - Docker images
)

if /i "!REMOVE_MODELS!"=="y" (
    if %SILENT_MODE% equ 0 echo   - AI model cache
)

if /i "!REMOVE_CONFIG!"=="y" (
    if %SILENT_MODE% equ 0 echo   - Configuration files
)

if %SILENT_MODE% equ 0 (
    echo.
    if /i not "!REMOVE_IMAGES!"=="y" (
        echo NOTE: Docker images were preserved.
        echo       Next installation will reuse existing images.
        echo.
    )
    if /i not "!REMOVE_VOLUMES!"=="y" (
        echo NOTE: Docker volumes were preserved.
        echo       Your transcription data is still available.
        echo.
    )
)

if %SILENT_MODE% equ 0 (
    echo.
    echo The OpenTranscribe program files will be removed by the Windows installer.
    echo.
    echo If you want to completely remove Docker Desktop ^(if no longer needed^):
    echo   1. Open Windows Settings
    echo   2. Go to Apps ^& Features
    echo   3. Uninstall Docker Desktop
    echo.
    echo To reinstall OpenTranscribe, run the installer again.
    echo.
    pause
)

endlocal
exit /b 0
