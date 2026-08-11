@echo off
echo ============================================================
echo   NotebookLM Authentication Setup
echo ============================================================
echo.
echo This script will open a Chromium browser window to log into your Google Account.
echo Once logged in, it will save your session cookies so the LangChain bot can
echo autonomously query your NotebookLM GoldShark notebook.
echo.

IF NOT EXIST "venv\Scripts\notebooklm.exe" (
    echo [ERROR] notebooklm package is not installed in the virtual environment.
    echo Please run 'pip install -r requirements.txt' first.
    pause
    exit /b 1
)

echo [1/2] Launching Google Login...
call venv\Scripts\notebooklm.exe login

echo.
echo [2/2] Checking for storage state...
IF EXIST "storage_state.json" (
    move /Y "storage_state.json" "data\storage_state.json" >nul
    echo.
    echo [SUCCESS] Authentication saved to data\storage_state.json
    echo The ContinualResearcher will now use your NotebookLM data.
) ELSE IF EXIST "context.json" (
    move /Y "context.json" "data\context.json" >nul
    echo.
    echo [SUCCESS] Authentication saved to data\context.json
    echo The ContinualResearcher will now use your NotebookLM data.
) ELSE (
    echo.
    echo [WARNING] No storage state file was generated. 
    echo If you see a storage_state.json file in another directory, move it to the 'data/' folder.
)

echo.
pause
