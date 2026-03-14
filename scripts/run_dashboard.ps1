# PowerShell script to run Streamlit dashboard
# Usage: .\scripts\run_dashboard.ps1

Write-Host "Starting Streamlit dashboard..." -ForegroundColor Green
py -m streamlit run src/dashboard/app.py --server.port 8501 --server.address 127.0.0.1

