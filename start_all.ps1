# Script khoi dong nhanh he thong IoT Smart Locker MVP (khong su dung icon/emoji)
$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$PythonExe = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$MySqlBin = "C:\Program Files\MySQL\MySQL Server 8.0\bin\mysqld.exe"
$MySqlAdmin = "C:\Program Files\MySQL\MySQL Server 8.0\bin\mysqladmin.exe"
$MySqlDataDir = (Join-Path $ProjectRoot "mysql_data") -replace '\\', '/'

if (-not (Test-Path $PythonExe)) {
    Write-Host "[LOI] Khong tim thay .venv tai $PythonExe. Vui long tao .venv va cai dat requirements truoc."
    exit 1
}

# 1. Kiem tra va khoi dong MySQL 8.0 neu cong 3306 chua lang nghe
$listening = Get-NetTCPConnection -LocalPort 3306 -State Listen -ErrorAction SilentlyContinue
if (-not $listening) {
    if (-not (Test-Path $MySqlBin)) {
        Write-Host "[LOI] Khong tim thay mysqld.exe tai $MySqlBin"
        exit 1
    }
    if (-not (Test-Path "$MySqlDataDir/mysql")) {
        Write-Host "[INFO] Khoi tao thu muc du lieu MySQL tai $MySqlDataDir ..."
        New-Item -ItemType Directory -Path $MySqlDataDir -Force | Out-Null
        & $MySqlBin --no-defaults --initialize-insecure --datadir="$MySqlDataDir"
    }
    Write-Host "[INFO] Dang khoi dong MySQL Server 8.0 tren 127.0.0.1:3306 ..."
    Start-Process -FilePath $MySqlBin -ArgumentList "--no-defaults", "--datadir=`"$MySqlDataDir`"", "--port=3306", "--bind-address=127.0.0.1", "--console" -WindowStyle Minimized

    $ready = $false
    for ($i = 0; $i -lt 30; $i++) {
        Start-Sleep -Seconds 1
        & $MySqlAdmin -h 127.0.0.1 -P 3306 -u root ping 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) {
            $ready = $true
            break
        }
    }
    if (-not $ready) {
        Write-Host "[LOI] MySQL khong san sang sau 30 giay."
        exit 1
    }
    Write-Host "[OK] MySQL Server da san sang."
} else {
    Write-Host "[OK] MySQL da dang chay tren cong 3306."
}

# 2. Chuan bi model AI va khoi tao du lieu mau
Write-Host "[INFO] Kiem tra model ONNX YuNet & SFace..."
& $PythonExe (Join-Path $ProjectRoot "backend\download_models.py")

Write-Host "[INFO] Khoi tao CSDL va du lieu mau..."
& $PythonExe (Join-Path $ProjectRoot "backend\seed.py")

# 3. Khoi chay 3 tien trinh: Backend (8000), Kiosk (8501), Dashboard (8502)
Write-Host "[INFO] Khoi chay Backend FastAPI (http://127.0.0.1:8000)..."
Start-Process -FilePath $PythonExe -ArgumentList "-m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000" -WorkingDirectory $ProjectRoot

Write-Host "[INFO] Khoi chay Kiosk Streamlit (http://127.0.0.1:8501)..."
Start-Process -FilePath $PythonExe -ArgumentList "-m streamlit run kiosk/app.py --server.port 8501" -WorkingDirectory $ProjectRoot
Start-Process -FilePath $PythonExe -ArgumentList "-m streamlit run kiosk/app.py --server.port 8501 --server.headless true" -WorkingDirectory $ProjectRoot

Write-Host "[INFO] Khoi chay Dashboard Streamlit (http://127.0.0.1:8502)..."
Start-Process -FilePath $PythonExe -ArgumentList "-m streamlit run dashboard/app.py --server.port 8502" -WorkingDirectory $ProjectRoot
Start-Process -FilePath $PythonExe -ArgumentList "-m streamlit run dashboard/app.py --server.port 8502 --server.headless true" -WorkingDirectory $ProjectRoot

Write-Host "[OK] He thong da duoc khoi chay:"
Write-Host " - Backend API Docs: http://127.0.0.1:8000/docs"
Write-Host " - Kiosk Khach hang: http://127.0.0.1:8501"
Write-Host " - Dashboard Quan tri: http://127.0.0.1:8502 (admin/admin123 hoac staff/staff123)"
