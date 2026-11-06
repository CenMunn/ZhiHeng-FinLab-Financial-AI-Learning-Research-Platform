param([int]$WebPort=5174,[int]$ApiPort=8010)
$ErrorActionPreference='Stop'
$projectPath=Split-Path $PSScriptRoot -Parent
$nodeCommand=Get-Command node -ErrorAction SilentlyContinue
$nodePath=if($nodeCommand){$nodeCommand.Source}else{Join-Path $env:USERPROFILE '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe'}
$pythonPath=Join-Path $projectPath 'backend/.venv/Scripts/python.exe'
$configPath=Join-Path $projectPath '.local/committee/config.json'
if(!(Test-Path -LiteralPath $configPath)){throw '请先按智投委接入说明生成运行包和本地配置。'}
$committeeConfig=Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
foreach($port in @($WebPort,$ApiPort,$committeeConfig.port,$committeeConfig.upstreamPort)){
    if(Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue){throw "端口 $port 已占用。不会结束已有进程；若平台已启动，请直接打开页面。"}
}
if(!(Test-Path -LiteralPath $nodePath) -or !(Test-Path -LiteralPath $pythonPath)){throw '找不到Node或后端虚拟环境，请先按README安装。'}
$committeeConfig.platformOrigin="http://127.0.0.1:$WebPort"
[System.IO.File]::WriteAllText($configPath,($committeeConfig | ConvertTo-Json),[System.Text.UTF8Encoding]::new($false))
$logs=Join-Path $projectPath '.local/platform'
New-Item -ItemType Directory -Path $logs -Force | Out-Null
$owned=@()
function Save-ProcessRecord {
    $processRecord=@{processes=$owned;webPort=$WebPort;apiPort=$ApiPort} | ConvertTo-Json -Depth 4
    [System.IO.File]::WriteAllText((Join-Path $logs 'processes.json'),$processRecord,[System.Text.UTF8Encoding]::new($false))
}
try {
$committee=Start-Process -FilePath $nodePath -ArgumentList @('"'+(Join-Path $projectPath 'scripts/start_committee.mjs')+'"') -WorkingDirectory $projectPath -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logs 'committee.log') -RedirectStandardError (Join-Path $logs 'committee-error.log') -PassThru
$owned+=@{role='committee';pid=$committee.Id;startedAt=$committee.StartTime.ToUniversalTime().ToString('o')}
Save-ProcessRecord
$backend=Start-Process -FilePath $pythonPath -ArgumentList @('-X','utf8','-m','uvicorn','platform_app.api.app:create_app','--factory','--app-dir','backend/src','--host','127.0.0.1','--port',"$ApiPort") -WorkingDirectory $projectPath -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logs 'backend.log') -RedirectStandardError (Join-Path $logs 'backend-error.log') -PassThru
$owned+=@{role='backend';pid=$backend.Id;startedAt=$backend.StartTime.ToUniversalTime().ToString('o')}
Save-ProcessRecord
$env:M1_API_PORT="$ApiPort"
$vite=Join-Path $projectPath 'apps/web/node_modules/vite/bin/vite.js'
$frontend=Start-Process -FilePath $nodePath -ArgumentList @('"'+$vite+'"','--host','127.0.0.1','--port',"$WebPort",'--strictPort') -WorkingDirectory (Join-Path $projectPath 'apps/web') -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logs 'frontend.log') -RedirectStandardError (Join-Path $logs 'frontend-error.log') -PassThru
$owned+=@{role='frontend';pid=$frontend.Id;startedAt=$frontend.StartTime.ToUniversalTime().ToString('o')}
Save-ProcessRecord
for($attempt=0;$attempt -lt 180;$attempt++){
    try{
        $status=Invoke-RestMethod "http://127.0.0.1:$ApiPort/api/v1/integrations/committee" -TimeoutSec 3
        $web=Invoke-WebRequest "http://127.0.0.1:$WebPort/" -TimeoutSec 3
        if($status.available -and $web.StatusCode -eq 200){Write-Host "平台已就绪：http://127.0.0.1:$WebPort/#/";exit 0}
    }catch{}
    Start-Sleep -Seconds 1
}
throw '服务尚未全部就绪，请查看 .local/platform 下的日志。'

} catch {
    $startupFailure=$_
    if($owned.Count){
        Save-ProcessRecord
        & $nodePath (Join-Path $projectPath 'scripts/stop_platform.mjs')
    }
    throw $startupFailure
}
