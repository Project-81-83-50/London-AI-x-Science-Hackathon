@echo off
rem Double-click to start the website: the API on port 8002 and the web page on port 5173, then open the browser.
rem Close the two server windows to stop it.
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo Creating the website's Python environment once...
  py -m venv .venv
  .venv\Scripts\python.exe -m pip install -r backend\app\requirements.txt
)
if not exist "frontend\node_modules" (
  echo Installing the website packages once...
  pushd frontend
  call npm install
  popd
)
if not exist "frontend\.env" (
  > "frontend\.env" echo VITE_API_URL=http://127.0.0.1:8002
)
rem The v3 Demo / Pipeline pages run lucas-sem-analysis-v3 with a Python that has PyTorch (see README).
if not exist "lucas-sem-analysis-v3\website\v3_python.txt" (
  python -c "import sys, torch; open(r'lucas-sem-analysis-v3\website\v3_python.txt', 'w').write(sys.executable)" 2>nul || (
    echo WARNING: no Python with PyTorch found - the Demo and Pipeline pages will not run new images.
    echo          Install it, see README "Quick start".
  )
)

start "EM QC API - port 8002" cmd /k ".venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --reload --port 8002"
start "EM QC website - port 5173" cmd /k "cd frontend && npm run dev"
echo Starting... the browser opens in a few seconds.
timeout /t 7 >nul
start "" http://localhost:5173
