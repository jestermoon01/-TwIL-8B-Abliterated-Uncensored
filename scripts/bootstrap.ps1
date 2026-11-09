$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$workspaceRoot = Split-Path $projectRoot -Parent
$artifactDir = Join-Path $workspaceRoot 'artifacts'
New-Item -ItemType Directory -Force $artifactDir | Out-Null

function Get-VerifiedArchive {
    param([string]$Url, [string]$Sha256, [string]$Destination)
    $archive = Join-Path $artifactDir ([System.IO.Path]::GetFileName($Url))
    if (!(Test-Path -LiteralPath $archive)) {
        Invoke-WebRequest -Uri $Url -OutFile $archive
    }
    if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant() -ne $Sha256) {
        throw "Checksum mismatch: $archive. Remove the invalid archive and retry."
    }
    Expand-Archive -LiteralPath $archive -DestinationPath $Destination -Force
}

Get-VerifiedArchive `
    -Url 'https://github.com/astral-sh/uv/releases/download/0.13.7/uv-x86_64-pc-windows-msvc.zip' `
    -Sha256 '0cdc5b38fe5a8168ed6a25814f5ba43c21d313dd3187314fccb37b7cec46e021' `
    -Destination (Join-Path $workspaceRoot 'tools/uv')

$engineDir = Join-Path $projectRoot 'bin-b10000'
Get-VerifiedArchive `
    -Url 'https://github.com/ggml-org/llama.cpp/releases/download/b10000/llama-b10000-bin-win-cuda-13.3-x64.zip' `
    -Sha256 '52612eb890cac41d4bdf35e56b82a45467af74986aff9a5b118f0c63b921ce59' `
    -Destination $engineDir
Get-VerifiedArchive `
    -Url 'https://github.com/ggml-org/llama.cpp/releases/download/b10000/cudart-llama-bin-win-cuda-13.3-x64.zip' `
    -Sha256 '1462a050eb4c684921ba51dcc4cc488a036674c3e73e9945ee705b854808d03e' `
    -Destination $engineDir

& (Join-Path $workspaceRoot 'tools/uv/uv.exe') sync --directory $projectRoot --locked
if ($LASTEXITCODE -ne 0) { throw 'uv sync failed' }
& (Join-Path $engineDir 'llama-server.exe') --version
if ($LASTEXITCODE -ne 0) { throw 'Engine startup failed; inspect the Windows C++ runtime' }
& (Join-Path $engineDir 'llama-server.exe') --list-devices
if ($LASTEXITCODE -ne 0) { throw 'CUDA device verification failed' }
