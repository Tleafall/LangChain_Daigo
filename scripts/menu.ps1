# ============================================================
# 予晴美粧代購 客服機器人 —— 主選單
# 由 start.bat 呼叫。也可以直接執行：powershell -ExecutionPolicy Bypass -File scripts\menu.ps1
# 加上 -Choice 數字 可以跳過選單直接執行，例如 -Choice 1
# 注意：這個檔案含中文，必須存成「UTF-8 with BOM」，Windows PowerShell 5.1 才不會亂碼。
# ============================================================
param([string]$Choice = "")

$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$OutputEncoding = [Text.Encoding]::UTF8
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONWARNINGS = "ignore"

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$Python = Join-Path $Root ".venv\Scripts\python.exe"

function Write-Title($text) { Write-Host "`n$text" -ForegroundColor Cyan }

# ---------- 檢查 Python 環境 ----------
if (-not (Test-Path $Python)) {
    Write-Host "找不到 Python 環境（.venv）。請先執行 setup.ps1 安裝。" -ForegroundColor Red
    exit 1
}

# ---------- 檢查 Ollama，沒開就幫忙打開 ----------
function Test-Ollama {
    try { Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:11434/api/version" -TimeoutSec 3 | Out-Null; return $true }
    catch { return $false }
}

function Start-OllamaIfNeeded {
    if (Test-Ollama) { return $true }
    Write-Host "Ollama 沒有在執行，正在幫你打開..." -ForegroundColor Yellow
    $dir = Join-Path $env:LOCALAPPDATA "Programs\Ollama"
    if (Test-Path (Join-Path $dir "ollama app.exe")) {
        Start-Process (Join-Path $dir "ollama app.exe")
    } elseif (Test-Path (Join-Path $dir "ollama.exe")) {
        Start-Process (Join-Path $dir "ollama.exe") -ArgumentList "serve" -WindowStyle Hidden
    } else {
        Write-Host "找不到 Ollama，請先安裝（見 docs\01_安裝教學.md）。" -ForegroundColor Red
        return $false
    }
    for ($i = 0; $i -lt 30; $i++) {
        Start-Sleep -Seconds 1
        if (Test-Ollama) { Write-Host "Ollama 已啟動。" -ForegroundColor Green; return $true }
    }
    Write-Host "Ollama 啟動失敗，請從開始選單手動打開 Ollama 再試一次。" -ForegroundColor Red
    return $false
}

# ---------- 各個功能 ----------
function Run-Py($script, $args2 = @()) {
    & $Python $script @args2
    if ($LASTEXITCODE -ne 0) { Write-Host "`n程式結束時出現錯誤（代碼 $LASTEXITCODE），請把上面的錯誤訊息截圖。" -ForegroundColor Red }
}

function Do-Chat {
    if (-not (Start-OllamaIfNeeded)) { return }
    Write-Title "啟動客服機器人（輸入 exit 離開，輸入 new 換新顧客）"
    Run-Py "src\step5_agent.py"
}

function Do-Demo {
    if (-not (Start-OllamaIfNeeded)) { return }
    Write-Title "自動示範：問 4 個問題"
    Run-Py "src\step5_agent.py" @("--demo")
}

function Do-Sync {
    Write-Title "從 yuchingmakeup.com 同步最新的商品和規則（約 1 分鐘）"
    Run-Py "scripts\sync_from_website.py"
}

function Do-Steps {
    if (-not (Start-OllamaIfNeeded)) { return }
    $steps = @(
        @("步驟 1：跟 AI 說第一句話", "src\step1_hello.py"),
        @("步驟 2：模板 + 管線", "src\step2_chain.py"),
        @("步驟 3：測試模型會不會用工具", "src\step3_tool_test.py"),
        @("步驟 4：RAG，先查規則再回答", "src\step4_rag_faq.py")
    )
    foreach ($s in $steps) {
        Write-Title ("=" * 50 + "`n" + $s[0] + "`n" + "=" * 50)
        Run-Py $s[1]
        if (-not $Choice) { Read-Host "`n按 Enter 繼續下一步" | Out-Null }
    }
}

# 注意：這裡不能用「回傳值」判斷要不要離開。
# PowerShell 函式會把裡面所有程式的輸出都當成回傳值，
# 如果寫成 (Invoke-Choice $c) -eq "exit" 或 | Out-Null，Python 印出來的字會全部被吞掉、畫面一片空白。
# 所以改用一個旗標 $script:Quit 來記錄。
$script:Quit = $false

function Invoke-Choice($c) {
    switch ($c) {
        "1" { Do-Chat }
        "2" { Do-Demo }
        "3" { Do-Sync }
        "4" { Do-Sync; Do-Chat }
        "5" { Do-Steps }
        "0" { $script:Quit = $true }
        default { Write-Host "請輸入選單上的數字。" -ForegroundColor Yellow }
    }
}

# ---------- 直接執行模式（-Choice）----------
if ($Choice) { Invoke-Choice $Choice; exit 0 }

# ---------- 選單模式 ----------
while ($true) {
    Write-Host ""
    Write-Host "==========================================" -ForegroundColor Magenta
    Write-Host "     予晴美粧代購 客服機器人（Gemma 4）" -ForegroundColor Magenta
    Write-Host "==========================================" -ForegroundColor Magenta
    Write-Host "  1. 開始跟客服聊天"
    Write-Host "  2. 自動示範（問 4 個問題，不用打字）"
    Write-Host "  3. 同步網站最新的商品和規則"
    Write-Host "  4. 先同步，再開始聊天"
    Write-Host "  5. 教學：依序執行步驟 1 到 4"
    Write-Host "  0. 離開"
    Write-Host ""
    $c = (Read-Host "請輸入數字").Trim()
    Invoke-Choice $c
    if ($script:Quit) { break }
}
