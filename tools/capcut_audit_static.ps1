$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$reportDir = Join-Path $PWD "capcut-audit-report"
New-Item -ItemType Directory -Force -Path $reportDir | Out-Null
$pkg = Join-Path $reportDir "CapCut_9_3_0_3970_installer.exe"
$url = "https://sf16-web-tos-buz.capcutstatic.com/obj/capcut-web-buz-sg/packages/CapCut_9_3_0_3970_capcutpc_0_creatortool.exe"
$expected = "09FC10FB852CA53973703AED909D83804FCC7EC40E7F843983E497146D57B4C5"
$metadata = [ordered]@{
  audit_date_utc = (Get-Date).ToUniversalTime().ToString("o")
  source_url = $url
  advertised_version = "9.3.0.3970"
  expected_sha256_from_winget = $expected
  downloaded = $false
  extraction_success = $false
  installer_executed = $false
}
try {
  Invoke-WebRequest -Uri $url -OutFile $pkg -MaximumRedirection 5 -TimeoutSec 900 -UseBasicParsing
  $metadata.downloaded = $true
  $metadata.file_bytes = (Get-Item $pkg).Length
  $metadata.actual_sha256 = (Get-FileHash -Algorithm SHA256 $pkg).Hash
  $metadata.sha256_verified = ($metadata.actual_sha256 -eq $expected)
  if (-not $metadata.sha256_verified) { throw "Installer SHA256 mismatch; refusing further processing" }
  $sig = Get-AuthenticodeSignature -FilePath $pkg
  $metadata.signature_status = [string]$sig.Status
  $metadata.signature_subject = if ($sig.SignerCertificate) { $sig.SignerCertificate.Subject } else { $null }
  $metadata.signature_issuer = if ($sig.SignerCertificate) { $sig.SignerCertificate.Issuer } else { $null }
  $seven = "C:\Program Files\7-Zip\7z.exe"
  if (-not (Test-Path $seven)) {
    $cmd = Get-Command 7z -ErrorAction SilentlyContinue
    if ($cmd) { $seven = $cmd.Source }
  }
  if (Test-Path $seven) {
    & $seven l -slt $pkg 2>&1 | Out-File -Encoding utf8 (Join-Path $reportDir "archive-list.txt")
    $dest = Join-Path $reportDir "extracted"
    New-Item -ItemType Directory -Force -Path $dest | Out-Null
    & $seven x -y "-o$dest" $pkg 2>&1 | Out-File -Encoding utf8 (Join-Path $reportDir "extraction-log.txt")
    $metadata.extractor_exit_code = $LASTEXITCODE
    $metadata.extraction_success = ($LASTEXITCODE -eq 0)
    if ($metadata.extraction_success) {
      $metadata.extracted_file_count = @(Get-ChildItem $dest -Recurse -File).Count
      $metadata.extracted_executables = @(Get-ChildItem $dest -Recurse -File -Filter "*.exe" | Select-Object -First 50 -ExpandProperty Name)
    }
  } else {
    $metadata.extraction_error = "7-Zip not available"
  }
} catch {
  $metadata.error = $_.Exception.Message
}
$metadata | ConvertTo-Json -Depth 10 | Out-File -Encoding utf8 (Join-Path $reportDir "installer-metadata.json")
$env:CAPCUT_AUDIT_DIR = $reportDir
python tools/capcut_audit_static.py
if ($LASTEXITCODE -ne 0) { Write-Warning "Python audit returned nonzero code" }
Write-Host "AUDIT_SUMMARY_BEGIN"
Get-Content (Join-Path $reportDir "audit-summary.md") -ErrorAction SilentlyContinue | Select-Object -First 180
Write-Host "AUDIT_SUMMARY_END"
if (-not $metadata.downloaded) { Write-Warning "Installer could not be downloaded: $($metadata.error)" }
if ($metadata.downloaded -and -not $metadata.sha256_verified) { exit 1 }
