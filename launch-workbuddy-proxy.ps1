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
        return $health.status -eq 'ok' -and $health.service -eq 'open-workbuddy'
    } catch {
        return $false
    }
}

function Test-PortInUse {
    try {
        $client = [System.Net.Sockets.TcpClient]::new()
        $async = $client.BeginConnect('127.0.0.1', $Port, $null, $null)
        $connected = $async.AsyncWaitHandle.WaitOne(750)
        if ($connected -and $client.Connected) {
            $client.EndConnect($async)
            return $true
        }
        return $false
    } catch {
        return $false
    } finally {
        if ($client) {
            $client.Dispose()
        }
    }
}

try {
    if (-not (Test-Path -LiteralPath $serverScript -PathType Leaf)) {
        throw "Proxy launcher script was not found: $serverScript"
    }

    if (Test-ProxyReady) {
        Write-LauncherLog "Proxy already running on port $Port. Reusing it."
    } else {
        if (Test-PortInUse) {
            throw "Port $Port is already occupied by a different service. Stop only the verified stale proxy process or rerun with -Port <free-port>."
        }
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
            throw "Proxy did not report healthy within 45 seconds. Check $serverErrorLog and $serverLog."
        }
    }

    try {
        Start-Process $dashboardUrl | Out-Null
        Write-LauncherLog "Opened $dashboardUrl."
    } catch {
        Write-LauncherLog "Proxy is healthy, but the dashboard could not be opened automatically: $($_.Exception.Message)"
        Write-Warning "Proxy is running at $dashboardUrl, but the dashboard could not be opened automatically."
    }
} catch {
    Write-LauncherLog "Launcher failed: $($_.Exception.Message)"
    throw
}
