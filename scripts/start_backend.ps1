param([int]$Port = 8010)
$ErrorActionPreference = 'Stop'
$projectPath = Split-Path $PSScriptRoot -Parent
$pythonPath = Join-Path $projectPath 'backend/.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw '请先按README创建后端虚拟环境。' }
if (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) {
    throw "端口 $Port 已被占用。请指定其他端口；不会结束已有进程。"
}
Set-Location -LiteralPath $projectPath
& $pythonPath -X utf8 -m uvicorn platform_app.api.app:create_app --factory --app-dir backend/src --host 127.0.0.1 --port $Port
