param(
  [string]$OutputDir = "tmp/release-record-example",
  [switch]$KeepOutput
)

$ErrorActionPreference = "Stop"

function Assert-Condition {
  param(
    [bool]$Condition,
    [string]$Message
  )

  if (-not $Condition) {
    throw $Message
  }
}

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

function New-ExampleBackupFileRecord {
  param(
    [string]$Path,
    [string]$Role,
    [string]$Content
  )

  [System.IO.File]::WriteAllText($Path, $Content, [System.Text.Encoding]::UTF8)
  $resolvedPath = Resolve-Path -LiteralPath $Path
  $item = Get-Item -LiteralPath $resolvedPath
  return [pscustomobject]@{
    role = $Role
    path = $resolvedPath.Path
    file_name = $item.Name
    bytes = $item.Length
    sha256 = Get-Sha256Hex -Path $resolvedPath.Path
  }
}

function New-ExampleBackupManifest {
  param([string]$Path)

  $outputDir = Split-Path -Parent $Path
  if ($outputDir) {
    New-Item -ItemType Directory -Force -Path $outputDir | Out-Null
  }
  $postgresRecord = New-ExampleBackupFileRecord `
    -Path (Join-Path $outputDir "postgres.dump") `
    -Role "postgres_dump" `
    -Content "example postgres dump for release record gate"
  $minioRecord = New-ExampleBackupFileRecord `
    -Path (Join-Path $outputDir "minio.tgz") `
    -Role "minio_archive" `
    -Content "example minio archive for release record gate"

  $manifest = [pscustomobject]@{
    generated_at = (Get-Date).ToUniversalTime().ToString("o")
    backup_version = "ielts-speaking-backup-v1"
    backup_dir = (Resolve-Path -LiteralPath $outputDir).Path
    postgres = [pscustomobject]@{
      user = "ielts"
      database = "ielts_speaking"
      dump = $postgresRecord
    }
    minio = [pscustomobject]@{
      alias = "local"
      bucket = "ielts-speaking-local"
      archive = $minioRecord
    }
  }

  $manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $Path -Encoding UTF8
}

$workspaceRoot = [System.IO.Path]::GetFullPath((Get-Location).Path)
$tmpRoot = [System.IO.Path]::GetFullPath((Join-Path $workspaceRoot "tmp"))
$resolvedOutputDir = [System.IO.Path]::GetFullPath((Join-Path $workspaceRoot $OutputDir))
$tmpRootWithSeparator = if ($tmpRoot.EndsWith([System.IO.Path]::DirectorySeparatorChar)) {
  $tmpRoot
} else {
  "$tmpRoot$([System.IO.Path]::DirectorySeparatorChar)"
}
if (-not ($resolvedOutputDir.StartsWith($tmpRootWithSeparator, [StringComparison]::OrdinalIgnoreCase))) {
  throw "OutputDir must resolve under workspace tmp/: $resolvedOutputDir"
}

if (Test-Path -LiteralPath $resolvedOutputDir) {
  Remove-Item -LiteralPath $resolvedOutputDir -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $resolvedOutputDir | Out-Null

$migrationAuditJson = Join-Path $resolvedOutputDir "migration-audit.json"
$migrationStatusBeforeRaw = Join-Path $resolvedOutputDir "migration-status-before.txt"
$migrationStatusAfterRaw = Join-Path $resolvedOutputDir "migration-status-after.txt"
$migrationStatusBeforeJson = Join-Path $resolvedOutputDir "migration-status-before.json"
$migrationStatusAfterJson = Join-Path $resolvedOutputDir "migration-status-after.json"
$stagingReadinessJson = Join-Path $resolvedOutputDir "staging-readiness.json"
$backupManifestJson = Join-Path $resolvedOutputDir "backup-manifest.json"
$backupIntegrityJson = Join-Path $resolvedOutputDir "backup-integrity.json"
$releaseRecordJson = Join-Path $resolvedOutputDir "release-record.json"

try {
  & (Join-Path $PSScriptRoot "audit_migrations.ps1") -OutputFile $migrationAuditJson | Out-Null
  $migrationAudit = Get-Content -Raw -LiteralPath $migrationAuditJson | ConvertFrom-Json
  $migrations = @($migrationAudit.migrations | Sort-Object version)
  $latestVersion = [int]$migrationAudit.latest_version
  $beforeLines = [System.Collections.Generic.List[string]]::new()
  $afterLines = [System.Collections.Generic.List[string]]::new()
  $beforeLines.Add("Applied At                  Migration")
  $beforeLines.Add("=======================================")
  $afterLines.Add("Applied At                  Migration")
  $afterLines.Add("=======================================")
  foreach ($migration in $migrations) {
    if ([int]$migration.version -eq $latestVersion) {
      $beforeLines.Add("Pending                     $($migration.file)")
    } else {
      $beforeLines.Add("2026-06-09T00:00:00Z        $($migration.file)")
    }
    $afterLines.Add("2026-06-09T00:00:00Z        $($migration.file)")
  }
  $beforeLines | Set-Content -LiteralPath $migrationStatusBeforeRaw -Encoding UTF8
  $afterLines | Set-Content -LiteralPath $migrationStatusAfterRaw -Encoding UTF8
  & (Join-Path $PSScriptRoot "capture_migration_status.ps1") `
    -Mode RawFile `
    -Phase pre `
    -RawStatusFile $migrationStatusBeforeRaw `
    -OutputFile $migrationStatusBeforeJson | Out-Null
  & (Join-Path $PSScriptRoot "capture_migration_status.ps1") `
    -Mode RawFile `
    -Phase post `
    -RawStatusFile $migrationStatusAfterRaw `
    -OutputFile $migrationStatusAfterJson | Out-Null
  & (Join-Path $PSScriptRoot "verify_staging_readiness.ps1") `
    -EnvFile ".env.staging.example" `
    -AllowExamplePlaceholders `
    -SkipRemoteChecks `
    -OutputFile $stagingReadinessJson | Out-Null
  New-ExampleBackupManifest -Path $backupManifestJson
  & (Join-Path $PSScriptRoot "verify_backup_manifest.ps1") `
    -Manifest $backupManifestJson `
    -OutputFile $backupIntegrityJson | Out-Null

  & (Join-Path $PSScriptRoot "generate_release_record.ps1") `
    -ReleaseOwner "ci-example" `
    -VersionTag "example-release-tag" `
    -RollbackDecisionOwner "ci-example" `
    -RollbackImageTag "previous-example-release-tag" `
    -ComposeEnvVersion "compose-env-example" `
    -MigrationAuditJson $migrationAuditJson `
    -MigrationStatusBeforeJson $migrationStatusBeforeJson `
    -MigrationStatusAfterJson $migrationStatusAfterJson `
    -StagingReadinessJson $stagingReadinessJson `
    -BackupManifest $backupManifestJson `
    -BackupIntegrityJson $backupIntegrityJson `
    -MonitoringWindow "15m" `
    -OutputFile $releaseRecordJson | Out-Null

  $record = Get-Content -Raw -LiteralPath $releaseRecordJson | ConvertFrom-Json
  Assert-Condition ($record.record_version -eq "release-record-v1") "release_record_version_mismatch"
  Assert-Condition ($record.passed -eq $true) "release_record_not_passed"
  Assert-Condition ($record.issue_count -eq 0) "release_record_has_issues"
  Assert-Condition ($record.evidence.migration_audit.passed -eq $true) "migration_audit_evidence_not_passed"
  Assert-Condition ($record.evidence.migration_status_before.phase -eq "pre") "migration_status_before_phase_mismatch"
  Assert-Condition ($record.evidence.migration_status_before.pending_count -eq 1) "migration_status_before_pending_count_mismatch"
  Assert-Condition ($record.evidence.migration_status_after.phase -eq "post") "migration_status_after_phase_mismatch"
  Assert-Condition ($record.evidence.migration_status_after.pending_count -eq 0) "migration_status_after_has_pending_migrations"
  Assert-Condition ($record.evidence.migration_status_after.latest_applied_version -eq $latestVersion) "migration_status_after_latest_version_mismatch"
  Assert-Condition ($record.evidence.staging_readiness.passed -eq $true) "staging_readiness_evidence_not_passed"
  Assert-Condition ([bool]$record.evidence.backup_manifest.postgres_sha256) "missing_postgres_backup_sha256"
  Assert-Condition ([bool]$record.evidence.backup_manifest.minio_sha256) "missing_minio_backup_sha256"
  Assert-Condition ($record.evidence.backup_integrity.passed -eq $true) "backup_integrity_not_passed"
  Assert-Condition ($record.evidence.backup_integrity.verified_file_count -eq 2) "backup_integrity_verified_file_count_mismatch"
  Assert-Condition ([bool]$record.evidence.migration_audit.file.sha256) "missing_migration_audit_file_sha256"
  Assert-Condition ([bool]$record.evidence.migration_status_before.file.sha256) "missing_migration_status_before_file_sha256"
  Assert-Condition ([bool]$record.evidence.migration_status_after.file.sha256) "missing_migration_status_after_file_sha256"
  Assert-Condition ([bool]$record.evidence.staging_readiness.file.sha256) "missing_staging_readiness_file_sha256"
  Assert-Condition ([bool]$record.evidence.backup_manifest.file.sha256) "missing_backup_manifest_file_sha256"
  Assert-Condition ([bool]$record.evidence.backup_integrity.file.sha256) "missing_backup_integrity_file_sha256"

  [pscustomobject]@{
    status = "passed"
    output_dir = (Resolve-Path -LiteralPath $resolvedOutputDir).Path
    release_record = (Resolve-Path -LiteralPath $releaseRecordJson).Path
    record_version = $record.record_version
    issue_count = $record.issue_count
  } | ConvertTo-Json -Depth 5
} finally {
  if (-not $KeepOutput -and (Test-Path -LiteralPath $resolvedOutputDir)) {
    Remove-Item -LiteralPath $resolvedOutputDir -Recurse -Force
  }
}
