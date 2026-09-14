param(
    [string]$Project = (Split-Path -Parent $MyInvocation.MyCommand.Path),
    [int]$Port = 40589,
    [string]$ShortcutName = 'Open WorkBuddy Proxy'
)

$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path -LiteralPath $Project).Path
$launcher = Join-Path $repo 'launch-workbuddy-proxy.ps1'
if (-not (Test-Path -LiteralPath $launcher -PathType Leaf)) {
    throw "Proxy launcher was not found: $launcher"
}

$desktop = [Environment]::GetFolderPath('Desktop')
if ([string]::IsNullOrWhiteSpace($desktop)) {
    throw 'Windows Desktop folder could not be resolved.'
}

$shell = New-Object -ComObject WScript.Shell
$pwsh = Get-Command pwsh.exe -ErrorAction SilentlyContinue
if (-not $pwsh) {
    $pwsh = Get-Command powershell.exe -ErrorAction Stop
}
$shortcutPath = Join-Path $desktop ($ShortcutName + '.lnk')
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $pwsh.Source
$shortcut.Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$launcher`" -Port $Port"
$shortcut.WorkingDirectory = $repo
$shortcut.Description = 'Start the local open-workbuddy proxy and open its dashboard.'
$shortcut.Save()

Write-Output "Created desktop shortcut: $shortcutPath"
