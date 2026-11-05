# Original CapCut 9.7 live runtime feasibility check, READ-ONLY.
# Does not launch, stop, inject, patch, click, connect to debugger ports, or modify CapCut.
# Writes one sanitized JSON report outside the CapCut install. Windows 10 / PowerShell 5.1.
[CmdletBinding()]
param(
    [string]$OutFile = ''
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$ExpectedVersion = '9.7.0.4153'
$ExpectedSuffix = "\Apps\$ExpectedVersion\CapCut.exe"
$checkedAt = (Get-Date).ToUniversalTime().ToString('o')

function Is-Loopback([string]$address) {
    return $address -eq '127.0.0.1' -or $address -eq '::1' -or $address -eq '[::1]'
}

if ([string]::IsNullOrWhiteSpace($OutFile)) {
    $base = Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'CapCutLiveBridgeCheck'
    $OutFile = Join-Path $base ('capcut-live-bridge-' + (Get-Date -Format 'yyyyMMdd_HHmmss') + '.json')
}
$OutFile = [IO.Path]::GetFullPath($OutFile)
$reportDir = Split-Path -Parent $OutFile

# Process query is limited to the running original application's registered path.
$rawProcesses = @()
$processQueryError = $null
try {
    $rawProcesses = @(Get-CimInstance Win32_Process -Filter "Name = 'CapCut.exe'" -ErrorAction Stop)
} catch {
    $processQueryError = 'Unable to enumerate running CapCut processes.'
}

$observations = @()
$installFolder = $null
$allTcpListeners = @()
$tcpQueryAvailable = $false
try {
    $allTcpListeners = @(Get-NetTCPConnection -State Listen -ErrorAction Stop)
    $tcpQueryAvailable = $true
} catch {
    # Networking query is optional; never change firewall settings.
}

foreach ($entry in $rawProcesses) {
    $exePath = [string]$entry.ExecutablePath
    if ([string]::IsNullOrWhiteSpace($exePath)) { continue }
    if (-not $exePath.EndsWith($ExpectedSuffix, [StringComparison]::OrdinalIgnoreCase)) { continue }

    $installFolder = Split-Path -Parent $exePath
    $pidNum = [int]$entry.ProcessId
    $moduleNames = @()
    $moduleQueryStatus = 'OK'
    try {
        $running = Get-Process -Id $pidNum -ErrorAction Stop
        $moduleNames = @($running.Modules | ForEach-Object { [string]$_.ModuleName } | Sort-Object -Unique)
    } catch {
        $moduleQueryStatus = 'ACCESS_DENIED_OR_UNAVAILABLE'
    }

    # Never persist raw process command lines: they may contain personal data.
    $cmd = [string]$entry.CommandLine
    $debuggerArg = $cmd -match '(?i)-qmljsdebugger\s*='
    $requestedPort = $null
    if ($cmd -match '(?i)-qmljsdebugger\s*=\s*port:(\d{2,5})') {
        $parsed = [int]$matches[1]
        if ($parsed -ge 1 -and $parsed -le 65535) { $requestedPort = $parsed }
    }

    $tcpList = @($allTcpListeners | Where-Object { [int]$_.OwningProcess -eq $pidNum })
    $loopbackPorts = @($tcpList | Where-Object { Is-Loopback ([string]$_.LocalAddress) } |
        ForEach-Object { [int]$_.LocalPort } | Sort-Object -Unique)
    $nonLoopback = @($tcpList | Where-Object { -not (Is-Loopback ([string]$_.LocalAddress)) })

    $qtModules = @($moduleNames | Where-Object { $_ -match '^(Qt[56](Core|Gui|Qml|Quick|Network)|VECreator|cccreator|videoeditor).*\.dll$' })
    $qmlModules = @($moduleNames | Where-Object { $_ -match '(?i)qml|qtquick' })
    $observations += [ordered]@{
        process_id = $pidNum
        exact_version_exe_path_matched = $true
        module_query_status = $moduleQueryStatus
        qt_runtime_module_names = $qtModules
        qml_related_module_names = $qmlModules
        qml_debugger_argument_present = [bool]$debuggerArg
        debugger_requested_port = $requestedPort
        loopback_listening_ports = $loopbackPorts
        nonloopback_listener_count = $nonLoopback.Count
    }
}

$toolingNames = @()
if ($null -ne $installFolder) {
    # Bounded directory listings: no recursive scan or extraction of vendor files.
    foreach ($relative in @('plugins\qmltooling', 'qmltooling')) {
        $folder = Join-Path $installFolder $relative
        if (Test-Path -LiteralPath $folder -PathType Container) {
            $toolingNames += @(Get-ChildItem -LiteralPath $folder -File -Filter '*qmldbg*.dll' -ErrorAction SilentlyContinue |
                ForEach-Object { $_.Name })
        }
    }
}
$toolingNames = @($toolingNames | Sort-Object -Unique)

$debugArgCount = @($observations | Where-Object { $_.qml_debugger_argument_present }).Count
$loopbackDebugCandidates = 0
foreach ($item in $observations) {
    if ($null -ne $item.debugger_requested_port -and
        @($item.loopback_listening_ports | Where-Object { $_ -eq $item.debugger_requested_port }).Count -gt 0) {
        $loopbackDebugCandidates += 1
    }
}

# A listening port is only a candidate, NOT verified QML debugger protocol.
$status = if ($null -ne $processQueryError) {
    'PROCESS_QUERY_UNAVAILABLE'
} elseif ($observations.Count -eq 0) {
    'ORIGINAL_CAPCUT_NOT_RUNNING'
} elseif ($loopbackDebugCandidates -gt 0) {
    'LOCAL_DEBUG_PORT_CANDIDATE_PROTOCOL_UNVERIFIED'
} elseif ($debugArgCount -gt 0) {
    'DEBUG_ARGUMENT_PRESENT_NO_MATCHING_LOOPBACK_PORT'
} else {
    'NO_LIVE_QML_DEBUG_ENTRYPOINT_OBSERVED'
}

$report = [ordered]@{
    schema = 'capcut-9.7-live-qt-bridge-feasibility-v1'
    observed_utc = $checkedAt
    target_version = $ExpectedVersion
    status = $status
    running_target_process_count = $observations.Count
    process_query_error = $processQueryError
    tcp_listener_query_available = $tcpQueryAvailable
    processes = $observations
    bundled_qml_debug_tooling_file_names = $toolingNames
    observed_loopback_debug_port_candidates = $loopbackDebugCandidates
    original_capcut_files_modified = $false
    drafts_read_or_modified = $false
    process_injection_or_attachment_attempted = $false
    debugger_port_connection_attempted = $false
    external_network_calls = $false
    live_qobject_verified = $false
    native_export_scheduler_abi_verified = $false
    unattended_capcut_mp4_export_verified = $false
    interpretation = 'Read-only live process metadata only. Qt debug plugins, module names, command flags or TCP ports do NOT prove a usable QML debugging server or private export API. Qt QML debugging must have been enabled in the vendor build; do not enable an exposed debug port on production.'
}

if ($installFolder -and $OutFile.StartsWith($installFolder + '\', [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Refusing to write the report inside original CapCut installation.'
}
if (-not (Test-Path -LiteralPath $reportDir)) {
    New-Item -ItemType Directory -Path $reportDir -Force | Out-Null
}
$report | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $OutFile -Encoding UTF8
Write-Output ('STATUS=' + $status)
Write-Output ('CAPCUT_PROCESS_COUNT=' + $observations.Count)
Write-Output ('LIVE_QOBJECT_VERIFIED=false')
Write-Output ('REPORT=' + $OutFile)
