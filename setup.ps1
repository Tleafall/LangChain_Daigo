# ============================================================
# 一鍵安裝腳本
# 用法：在專案資料夾打開 PowerShell，執行  .\setup.ps1
# 如果出現「無法載入，因為這個系統上已停用指令碼執行」，先執行：
#   Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
# ============================================================

$ErrorActionPreference = "Stop"
$Model = "gemma4:e4b"

Write-Host "`n[1/4] 檢查 Python..." -ForegroundColor Cyan
try { py -3.11 --version } catch {
    Write-Host "找不到 Python 3.11，請先到 https://www.python.org 安裝（安裝時勾選 Add to PATH）" -ForegroundColor Red
    exit 1
}

Write-Host "`n[2/4] 檢查 Ollama..." -ForegroundColor Cyan
$ollama = Get-Command ollama -ErrorAction SilentlyContinue
if (-not $ollama) {
    $cand = "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe"
    if (Test-Path $cand) { $ollama = $cand } else {
        Write-Host "找不到 Ollama，正在用 winget 安裝..." -ForegroundColor Yellow
        winget install --id Ollama.Ollama -e --accept-package-agreements --accept-source-agreements
        $ollama = $cand
    }
} else { $ollama = $ollama.Source }
& $ollama --version

Write-Host "`n[3/4] 下載模型 $Model（約 7~10GB，第一次會很久）..." -ForegroundColor Cyan
& $ollama pull $Model

Write-Host "`n[4/4] 建立 Python 虛擬環境並安裝套件..." -ForegroundColor Cyan
if (-not (Test-Path ".venv")) { py -3.11 -m venv .venv }
& ".\.venv\Scripts\python.exe" -m pip install --upgrade pip
& ".\.venv\Scripts\python.exe" -m pip install -r requirements.txt

Write-Host "`n安裝完成！接下來執行：" -ForegroundColor Green
Write-Host "  .\.venv\Scripts\Activate.ps1"
Write-Host "  python src\step1_hello.py"
