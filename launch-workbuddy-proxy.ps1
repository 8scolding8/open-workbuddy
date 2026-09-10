param(
    [int]$Port = 40589
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $MyInvocation.MyCommand.Path
$serverScript = Join-Path $repo 'start-windows.ps1'
$runtimeDir = Join-Path $repo '.proxy-runtime'
$launcherLog = Join-Path $runtimeDir 'desktop-launcher.log'
$serverLog = Join-Path $runtimeDir 'desktop-server.log'
$serverErrorLog = Join-Path $runtimeDir 'desktop-server-error.log'
$dashboardUrl = "http://localhost:$Port/#integrations/keys"
$healthUrl = "http://127.0.0.1:$Port/health"

New-Item -ItemType Directory -Path $runtimeDir -Force | Out-Null

function Write-LauncherLog {
    param([string]$Message)
    Add-Content -LiteralPath $launcherLog -Value ("{0:u} {1}" -f (Get-Date), $Message)
}

function Test-ProxyReady {
    try {
        $health = Invoke-RestMethod -Uri $healthUrl -Method Get -TimeoutSec 2
        return $health.status -eq 'ok'
    } catch {
        return $false
    }
}

try {
    if (-not (Test-Path -LiteralPath $serverScript -PathType Leaf)) {
        throw "Proxy launcher script was not found: $serverScript"
    }

    if (Test-ProxyReady) {
        Write-LauncherLog "Proxy already running on port $Port. Reusing it."
    } else {
        $pwsh = Join-Path $PSHOME 'pwsh.exe'
        if (-not (Test-Path -LiteralPath $pwsh -PathType Leaf)) {
            $pwshCommand = Get-Command pwsh.exe -ErrorAction SilentlyContinue
            if ($pwshCommand) {
                $pwsh = $pwshCommand.Source
            } else {
                $pwsh = (Get-Command powershell.exe -ErrorAction Stop).Source
            }
        }
        $serverArguments = "-NoProfile -ExecutionPolicy Bypass -File `"$serverScript`" -Project `"$repo`" -Port $Port"
        $process = Start-Process `
            -FilePath $pwsh `
            -ArgumentList $serverArguments `
            -WorkingDirectory $repo `
            -WindowStyle Hidden `
            -RedirectStandardOutput $serverLog `
            -RedirectStandardError $serverErrorLog `
            -PassThru
        Write-LauncherLog "Started hidden proxy process $($process.Id) on port $Port."

        $deadline = (Get-Date).AddSeconds(45)
        while ((Get-Date) -lt $deadline -and -not (Test-ProxyReady)) {
            Start-Sleep -Milliseconds 500
        }
        if (Test-ProxyReady) {
            Write-LauncherLog "Proxy health check passed."
        } else {
            Write-LauncherLog "Proxy did not report healthy within 45 seconds; opening dashboard anyway."
        }
    }

    Start-Process $dashboardUrl | Out-Null
    Write-LauncherLog "Opened $dashboardUrl."
} catch {
    Write-LauncherLog "Launcher failed: $($_.Exception.Message)"
    throw
}
