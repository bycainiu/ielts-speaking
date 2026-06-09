param(
  [Parameter(Mandatory = $true)]
  [string]$Manifest,
  [string]$OutputFile
)

$ErrorActionPreference = "Stop"

function Get-Sha256Hex {
  param([string]$Path)

  if (Get-Command Get-FileHash -ErrorAction SilentlyContinue) {
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
  }

  $stream = [System.IO.File]::OpenRead((Resolve-Path -LiteralPath $Path).Path)
  try {
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try {
      $bytes = $sha.ComputeHash($stream)
      return ([System.BitConverter]::ToString($bytes)).Replace("-", "").ToLowerInvariant()
    } finally {
      $sha.Dispose()
    }
  } finally {
    $stream.Dispose()
  }
}

function Resolve-BackupFilePath {
  param(
    [object]$ManifestJson,
    [object]$Record,
    [string]$FallbackFileName
  )

  $candidates = [System.Collections.Generic.List[string]]::new()
  if ($Record -and $Record.path) {
    $candidates.Add([string]$Record.path)
  }
  if ($ManifestJson.backup_dir -and $Record -and $Record.file_name) {
    $candidates.Add((Join-Path ([string]$ManifestJson.backup_dir) ([string]$Record.file_name)))
  }
  if ($ManifestJson.backup_dir) {
    $candidates.Add((Join-Path ([string]$ManifestJson.backup_dir) $FallbackFileName))
  }

  foreach ($candidate in $candidates) {
    if ($candidate -and (Test-Path -LiteralPath $candidate)) {
      return (Resolve-Path -LiteralPath $candidate).Path
    }
  }
  return if ($candidates.Count -gt 0) { $candidates[0] } else { $FallbackFileName }
}

function Test-BackupRecord {
  param(
    [object]$ManifestJson,
    [object]$Record,
    [string]$Role,
    [string]$FallbackFileName,
    [System.Collections.Generic.List[string]]$Issues
  )

  $path = Resolve-BackupFilePath -ManifestJson $ManifestJson -Record $Record -FallbackFileName $FallbackFileName
  if (-not (Test-Path -LiteralPath $path)) {
    $Issues.Add("missing_backup_file:$Role")
    return [pscustomobject]@{
      role = $Role
      path = $path
      exists = $false
      expected_bytes = if ($Record) { $Record.bytes } else { $null }
      actual_bytes = $null
      expected_sha256 = if ($Record) { $Record.sha256 } else { $null }
      actual_sha256 = $null
      verified = $false
    }
  }

  $resolvedPath = Resolve-Path -LiteralPath $path
  $item = Get-Item -LiteralPath $resolvedPath
  $actualHash = Get-Sha256Hex -Path $resolvedPath.Path
  $expectedBytes = if ($Record) { $Record.bytes } else { $null }
  $expectedHash = if ($Record) { [string]$Record.sha256 } else { "" }
  $verified = $true

  if ($null -eq $expectedBytes) {
    $Issues.Add("missing_expected_bytes:$Role")
    $verified = $false
  } elseif ([int64]$expectedBytes -ne [int64]$item.Length) {
    $Issues.Add("backup_size_mismatch:$Role")
    $verified = $false
  }

  if (-not $expectedHash) {
    $Issues.Add("missing_expected_sha256:$Role")
    $verified = $false
  } elseif ($expectedHash.ToLowerInvariant() -ne $actualHash) {
    $Issues.Add("backup_sha256_mismatch:$Role")
    $verified = $false
  }

  [pscustomobject]@{
    role = $Role
    path = $resolvedPath.Path
    exists = $true
    expected_bytes = $expectedBytes
    actual_bytes = $item.Length
    expected_sha256 = $expectedHash
    actual_sha256 = $actualHash
    verified = $verified
  }
}

$issues = [System.Collections.Generic.List[string]]::new()
$resolvedManifest = Resolve-Path -LiteralPath $Manifest
$manifestJson = Get-Content -Raw -LiteralPath $resolvedManifest | ConvertFrom-Json

if ($manifestJson.backup_version -ne "ielts-speaking-backup-v1") {
  $issues.Add("unsupported_backup_manifest_version")
}
if (-not $manifestJson.backup_dir) {
  $issues.Add("missing_backup_dir")
}
if (-not $manifestJson.postgres.dump) {
  $issues.Add("missing_postgres_dump_record")
}
if (-not $manifestJson.minio.archive) {
  $issues.Add("missing_minio_archive_record")
}

$fileChecks = @(
  Test-BackupRecord -ManifestJson $manifestJson -Record $manifestJson.postgres.dump -Role "postgres_dump" -FallbackFileName "postgres.dump" -Issues $issues
  Test-BackupRecord -ManifestJson $manifestJson -Record $manifestJson.minio.archive -Role "minio_archive" -FallbackFileName "minio.tgz" -Issues $issues
)

$evidence = [pscustomobject]@{
  generated_at = (Get-Date).ToUniversalTime().ToString("o")
  evidence_version = "backup-integrity-evidence-v1"
  manifest = $resolvedManifest.Path
  backup_version = $manifestJson.backup_version
  backup_dir = $manifestJson.backup_dir
  verified_file_count = @($fileChecks | Where-Object { $_.verified }).Count
  file_checks = $fileChecks
  issue_count = $issues.Count
  issues = $issues
  passed = ($issues.Count -eq 0)
}

$json = $evidence | ConvertTo-Json -Depth 8
if ($OutputFile) {
  $outputDir = Split-Path -Parent $OutputFile
  if ($outputDir) {
    New-Item -ItemType Directory -Force -Path $outputDir | Out-Null
  }
  Set-Content -LiteralPath $OutputFile -Value $json -Encoding UTF8
}
$json

if ($issues.Count -gt 0) {
  exit 1
}
