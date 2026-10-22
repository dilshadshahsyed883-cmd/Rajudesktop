<#
.SYNOPSIS
  Owner-triggered offline installation/upgrade of a VERIFIED Rajudesktop Windows ZIP.
.DESCRIPTION
  No GitHub/VPS/Tailscale connection is initiated here. Operator first downloads
  the exact immutable artifact over an approved route, then invokes this script
  manually on the target Windows machine (locally or via Windows OpenSSH over Tailscale).
  NEVER deletes project data, imported media, OAuth files or other applications.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$ArtifactZip,
    [Parameter(Mandatory=$true)][string]$ChecksumFile,
    [string]$InstallRoot = (Join-Path $env:LOCALAPPDATA 'Rajudesktop\SceneDesktopStudio'),
    [switch]$SkipLaunchSmoke
)
$ErrorActionPreference = 'Stop'
$zip = (Resolve-Path -LiteralPath $ArtifactZip).Path
$hashPath = (Resolve-Path -LiteralPath $ChecksumFile).Path
if ([IO.Path]::GetExtension($zip).ToLowerInvariant() -ne '.zip') { throw "A Windows ZIP artifact is required" }
$expected = ([IO.File]::ReadAllText($hashPath) -split '\s+')[0].Trim().ToUpperInvariant()
if ($expected -notmatch '^[A-F0-9]{64}$') { throw "Invalid SHA256 sidecar file" }
$actual = (Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash
if ($actual -ne $expected) { throw "Build hash mismatch. Installation blocked." }
if (Get-Process -Name 'SceneDesktopStudio' -ErrorAction SilentlyContinue) {
    throw "SceneDesktopStudio is running. Save work and close it first."
}

$root = [IO.Path]::GetFullPath($InstallRoot)
$cache = Join-Path $root 'work'
$backupDir = Join-Path $root 'backups'
$current = Join-Path $root 'current'
New-Item -Path $root,$backupDir,$cache -ItemType Directory -Force | Out-Null
$stage = Join-Path $cache ("stage-" + [Guid]::NewGuid().ToString('N'))
$backup = Join-Path $backupDir ("release-" + (Get-Date -Format "yyyyMMdd-HHmmss") + "-" + [Guid]::NewGuid().ToString('N'))
New-Item -Path $stage -ItemType Directory | Out-Null
$installed = $false
$backedUp = $false
try {
    Expand-Archive -LiteralPath $zip -DestinationPath $stage -Force
    $app = Join-Path $stage 'SceneDesktopStudio'
    if (!(Test-Path -LiteralPath (Join-Path $app 'SceneDesktopStudio.exe'))) {
        throw "ZIP is missing SceneDesktopStudio/SceneDesktopStudio.exe"
    }
    $manifest = Join-Path $app 'build-manifest.json'
    if (!(Test-Path -LiteralPath $manifest)) { throw "Missing build manifest" }
    $meta = Get-Content -LiteralPath $manifest -Raw | ConvertFrom-Json
    $exeHash = (Get-FileHash -LiteralPath (Join-Path $app 'SceneDesktopStudio.exe') -Algorithm SHA256).Hash
    if ($exeHash -ne $meta.executable_sha256) { throw "Executable does not match build manifest" }
    if (Test-Path -LiteralPath $current) {
        Move-Item -LiteralPath $current -Destination $backup
        $backedUp = $true
    }
    Move-Item -LiteralPath $app -Destination $current
    $installed = $true
    if (!$SkipLaunchSmoke) {
        # The actual GUI must be opened in an interactive user session.
        # Remote OpenSSH service sessions must NOT attempt a false GUI health test.
        if (-not [Environment]::UserInteractive) {
            throw "Interactive Windows user session required for GUI smoke; rerun locally or use -SkipLaunchSmoke"
        }
        $process = Start-Process -FilePath (Join-Path $current 'SceneDesktopStudio.exe') -PassThru
        Start-Sleep -Seconds 4
        $process.Refresh()
        if ($process.HasExited) { throw "Desktop app exited during launch; installation will roll back" }
        Stop-Process -Id $process.Id -ErrorAction SilentlyContinue
    }
    $receipt = [ordered]@{
        result = 'MANUAL_INSTALL_PASS'
        installed_at = (Get-Date).ToString('o')
        source_sha = [string]$meta.build_sha
        artifact_sha256 = $actual
        installed_executable_sha256 = $exeHash
        path = $current
        backup = $(if ($backedUp) { $backup } else { $null })
        smoke_skipped = [bool]$SkipLaunchSmoke
    }
    $receipt | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $root 'last-install.json') -Encoding UTF8
    $receipt | ConvertTo-Json
}
catch {
    $originalError = $_
    if ($installed -and (Test-Path -LiteralPath $current)) {
        # Only our own installation directory is removed during failed staging.
        Remove-Item -LiteralPath $current -Recurse -Force
    }
    if ($backedUp -and (Test-Path -LiteralPath $backup)) {
        Move-Item -LiteralPath $backup -Destination $current
    }
    throw "Manual deployment failed (app-only rollback attempted): $originalError"
}
finally {
    if (Test-Path -LiteralPath $stage) { Remove-Item -LiteralPath $stage -Recurse -Force }
}
