param([switch]$WaitForWheel)
$ErrorActionPreference='Stop'
$projectPath=Split-Path $PSScriptRoot -Parent
Set-Location -LiteralPath $projectPath
$trainingPython=Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
$cudaWheel=Join-Path $projectPath '.local/wheels/torch-2.10.0+cu128-cp312-cp312-win_amd64.whl'
$outputPath=Join-Path $PSScriptRoot 'artifacts/b012-20261030'
New-Item -ItemType Directory -Path $outputPath -Force | Out-Null
$utf8=[System.Text.UTF8Encoding]::new($false)
$env:PYTHONUTF8='1'
$env:PYTHONUNBUFFERED='1'
$env:TOKENIZERS_PARALLELISM='false'
$env:OMP_NUM_THREADS='2'
$env:MKL_NUM_THREADS='2'
# Refuse before touching pipeline state or regenerating any existing predictions.
foreach($existingSeed in @(42,43,44)){
    if(Test-Path -LiteralPath (Join-Path $outputPath "b2-seed-$existingSeed")){
        throw 'Existing training run found. Use a new versioned experiment instead of overwriting it.'
    }
}
function Run-Stage([string]$stage,[string[]]$arguments){
    [System.IO.File]::WriteAllText((Join-Path $outputPath 'pipeline-state.json'),(@{stage=$stage;status='running';utc=[DateTime]::UtcNow.ToString('o')} | ConvertTo-Json),$utf8)
    & $trainingPython @arguments
    if($LASTEXITCODE -ne 0){throw "Stage failed: $stage (exit $LASTEXITCODE)"}
}
try {
    if($WaitForWheel){while(!(Test-Path -LiteralPath $cudaWheel)){Start-Sleep -Seconds 5}}
    if(!(Test-Path -LiteralPath $cudaWheel)){throw 'Verified CUDA wheel is not available.'}
    $actualHash=(Get-FileHash -LiteralPath $cudaWheel -Algorithm SHA256).Hash.ToLowerInvariant()
    if($actualHash -ne 'fbde8f6a9ec8c76979a0d14df21c10b9e5cab6f0d106a73ca73e2179bc597cae'){throw 'Official CUDA wheel hash mismatch.'}
    Run-Stage 'install-cuda' @('-m','pip','install',$cudaWheel,'--no-cache-dir','--timeout','30','--retries','2')
    Run-Stage 'pip-check' @('-m','pip','check')
    $frozen=& $trainingPython -m pip freeze
    if($LASTEXITCODE -ne 0){throw 'Cannot freeze environment'}
    $portable=$frozen | ForEach-Object {if($_ -match '^torch @ '){'torch==2.10.0+cu128'}else{$_}}
    [System.IO.File]::WriteAllText((Join-Path $PSScriptRoot 'requirements-training.lock.txt'),("--extra-index-url https://download.pytorch.org/whl/cu128`n"+($portable -join "`n")+"`n"),$utf8)
    Run-Stage 'unit-tests' @('-X','utf8','-m','unittest','discover','-s','research/tests')
    Run-Stage 'environment-inventory' @('-X','utf8','-m','research.training.probe_environment','--torch-smoke','--output', (Join-Path $outputPath 'environment.json'))
    Run-Stage 'model-smoke' @('-X','utf8','-m','research.training.run_ranking','smoke')
    Run-Stage 'bm25' @('-X','utf8','-m','research.training.run_ranking','bm25')
    Run-Stage 'pretrained' @('-X','utf8','-m','research.training.run_ranking','pretrained')
    foreach($trainingSeed in @(42,43,44)){
        Run-Stage "train-$trainingSeed" @('-X','utf8','-m','research.training.run_ranking','train','--seed',"$trainingSeed")
        Run-Stage "predict-$trainingSeed" @('-X','utf8','-m','research.training.run_ranking','predict','--seed',"$trainingSeed")
    }
    Run-Stage 'summarize' @('-X','utf8','-m','research.training.run_ranking','summarize')
    [System.IO.File]::WriteAllText((Join-Path $outputPath 'pipeline-state.json'),(@{stage='finished';status='completed';utc=[DateTime]::UtcNow.ToString('o')} | ConvertTo-Json),$utf8)
} catch {
    [System.IO.File]::WriteAllText((Join-Path $outputPath 'pipeline-state.json'),(@{status='failed';error=$_.Exception.Message;utc=[DateTime]::UtcNow.ToString('o')} | ConvertTo-Json),$utf8)
    throw
}
