param([int]$Port = 5174, [int]$ApiPort = 8010)
$ErrorActionPreference = 'Stop'
$projectPath = Split-Path $PSScriptRoot -Parent
if (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) {
    throw "端口 $Port 已被占用。请指定其他端口；不会结束已有进程。"
}
$env:M1_API_PORT = "$ApiPort"
Set-Location -LiteralPath $projectPath
$pnpmCommand = Get-Command pnpm -ErrorAction SilentlyContinue
if ($pnpmCommand) {
    & $pnpmCommand.Source --dir apps/web dev --host 127.0.0.1 --port $Port --strictPort
} else {
    $runtimePath = Join-Path $env:USERPROFILE '.cache/codex-runtimes/codex-primary-runtime/dependencies'
    $pnpmPath = Join-Path $runtimePath 'bin/fallback/pnpm.cmd'
    $nodePath = Join-Path $runtimePath 'node/bin'
    if (-not (Test-Path -LiteralPath $pnpmPath)) { throw '找不到pnpm。请安装Node.js与pnpm，或使用Codex内置运行时。' }
    $env:PATH = "$nodePath;$env:PATH"
    & $pnpmPath --dir apps/web dev --host 127.0.0.1 --port $Port --strictPort
}
