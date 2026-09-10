param(
    [string]$Project = (Get-Location).Path,
    [int]$Port = 40589
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $MyInvocation.MyCommand.Path
$configuredCli = [Environment]::GetEnvironmentVariable('WORKBUDDY_CLI_PATH')
$cli = if ([string]::IsNullOrWhiteSpace($configuredCli)) {
    Join-Path $env:LOCALAPPDATA 'Programs\WorkBuddy\resources\app.asar.unpacked\cli\bin\codebuddy'
} else {
    [Environment]::ExpandEnvironmentVariables($configuredCli.Trim())
}

if (-not (Test-Path -LiteralPath $cli -PathType Leaf)) {
    throw "WorkBuddy codebuddy launcher was not found at $cli. Set WORKBUDDY_CLI_PATH to the installed launcher and rerun."
}
$node = Get-ChildItem -LiteralPath (Join-Path $env:USERPROFILE '.workbuddy\binaries\node\versions') -Recurse -Filter 'node.exe' -File -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1
if ($node) {
    $env:CODEBUDDY_NODE_BIN = $node.FullName
}

$venvPython = Join-Path $repo '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) {
    throw "Python environment is missing: $venvPython. Create it with: py -m venv .venv; .\.venv\Scripts\python.exe -m pip install -r requirements-windows.txt"
}

$env:FREEMODEL_BASE_URL = 'https://work.freemodel.dev/v1'
$env:FREEMODEL_TRANSPORT = 'workbuddy_acp'
$env:WORKBUDDY_CLI_PATH = $cli
$env:PROXY_DEFAULT_PROJECT = (Resolve-Path -LiteralPath $Project).Path
$env:PROXY_HOST = '127.0.0.1'
$env:PROXY_PORT = [string]$Port

& $venvPython (Join-Path $repo 'proxy_server.py')
