param(
  [Parameter(Mandatory = $true)]
  [string]$ReleaseOwner,
  [Parameter(Mandatory = $true)]
  [string]$VersionTag,
  [Parameter(Mandatory = $true)]
  [string]$RollbackDecisionOwner,
  [Parameter(Mandatory = $true)]
  [string]$MigrationAuditJson,
  [Parameter(Mandatory = $true)]
  [string]$MigrationStatusBeforeJson,
  [Parameter(Mandatory = $true)]
  [string]$MigrationStatusAfterJson,
  [Parameter(Mandatory = $true)]
  [string]$StagingReadinessJson,
  [Parameter(Mandatory = $true)]
  [string]$BackupManifest,
  [Parameter(Mandatory = $true)]
  [string]$BackupIntegrityJson,
  [string]$RollbackImageTag,
  [string]$ComposeEnvVersion,
  [string]$MigrationVersion,
  [string]$MonitoringWindow = "60m",
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

function Read-EvidenceJson {
  param(
    [string]$Path,
    [string]$Name,
    [System.Collections.Generic.List[string]]$Issues
  )

  if (-not (Test-Path -LiteralPath $Path)) {
    $Issues.Add("missing_evidence:$Name")
    return $null
  }

  try {
    return Get-Content -Raw -LiteralPath $Path | ConvertFrom-Json
  } catch {
    $Issues.Add("invalid_json:$Name")
    return $null
  }
}

function Evidence-FileRecord {
  param(
    [string]$Path,
    [string]$Name,
    [System.Collections.Generic.List[string]]$Issues
  )

  if (-not (Test-Path -LiteralPath $Path)) {
    $Issues.Add("missing_evidence_file:$Name")
    return $null
  }

  $resolvedPath = Resolve-Path -LiteralPath $Path
  $item = Get-Item -LiteralPath $resolvedPath
  return [pscustomobject]@{
    path = $resolvedPath.Path
    file_name = $item.Name
    bytes = $item.Length
    sha256 = Get-Sha256Hex -Path $resolvedPath.Path
  }
}

$issues = [System.Collections.Generic.List[string]]::new()

if ([string]::IsNullOrWhiteSpace($ReleaseOwner)) {
  $issues.Add("missing_release_owner")
}
if ([string]::IsNullOrWhiteSpace($VersionTag)) {
  $issues.Add("missing_version_tag")
}
if ([string]::IsNullOrWhiteSpace($RollbackDecisionOwner)) {
  $issues.Add("missing_rollback_decision_owner")
}
if ([string]::IsNullOrWhiteSpace($RollbackImageTag)) {
  $issues.Add("missing_rollback_image_tag")
}
if ([string]::IsNullOrWhiteSpace($ComposeEnvVersion)) {
  $issues.Add("missing_compose_env_version")
}

$migrationAudit = Read-EvidenceJson -Path $MigrationAuditJson -Name "migration_audit" -Issues $issues
$migrationStatusBefore = Read-EvidenceJson -Path $MigrationStatusBeforeJson -Name "migration_status_before" -Issues $issues
$migrationStatusAfter = Read-EvidenceJson -Path $MigrationStatusAfterJson -Name "migration_status_after" -Issues $issues
$stagingReadiness = Read-EvidenceJson -Path $StagingReadinessJson -Name "staging_readiness" -Issues $issues
$backupManifestJson = Read-EvidenceJson -Path $BackupManifest -Name "backup_manifest" -Issues $issues
$backupIntegrity = Read-EvidenceJson -Path $BackupIntegrityJson -Name "backup_integrity" -Issues $issues

$migrationAuditFile = Evidence-FileRecord -Path $MigrationAuditJson -Name "migration_audit" -Issues $issues
$migrationStatusBeforeFile = Evidence-FileRecord -Path $MigrationStatusBeforeJson -Name "migration_status_before" -Issues $issues
$migrationStatusAfterFile = Evidence-FileRecord -Path $MigrationStatusAfterJson -Name "migration_status_after" -Issues $issues
$stagingReadinessFile = Evidence-FileRecord -Path $StagingReadinessJson -Name "staging_readiness" -Issues $issues
$backupManifestFile = Evidence-FileRecord -Path $BackupManifest -Name "backup_manifest" -Issues $issues
$backupIntegrityFile = Evidence-FileRecord -Path $BackupIntegrityJson -Name "backup_integrity" -Issues $issues

if ($migrationAudit) {
  if ($migrationAudit.audit_version -ne "migration-audit-v1") {
    $issues.Add("unsupported_migration_audit_version")
  }
  if ($migrationAudit.passed -ne $true) {
    $issues.Add("migration_audit_not_passed")
  }
  if ($migrationAudit.issue_count -gt 0) {
    $issues.Add("migration_audit_has_issues")
  }
}

if ($migrationStatusBefore) {
  if ($migrationStatusBefore.evidence_version -ne "migration-status-evidence-v1") {
    $issues.Add("unsupported_migration_status_before_version")
  }
  if ($migrationStatusBefore.phase -ne "pre") {
    $issues.Add("migration_status_before_phase_mismatch")
  }
  if ($migrationStatusBefore.exit_code -ne 0) {
    $issues.Add("migration_status_before_command_failed")
  }
  if (-not $migrationStatusBefore.raw_stdout) {
    $issues.Add("migration_status_before_missing_raw_stdout")
  }
  if ($migrationStatusBefore.issue_count -gt 0 -or $migrationStatusBefore.passed -ne $true) {
    $issues.Add("migration_status_before_has_issues")
  }
}

if ($migrationStatusAfter) {
  if ($migrationStatusAfter.evidence_version -ne "migration-status-evidence-v1") {
    $issues.Add("unsupported_migration_status_after_version")
  }
  if ($migrationStatusAfter.phase -ne "post") {
    $issues.Add("migration_status_after_phase_mismatch")
  }
  if ($migrationStatusAfter.exit_code -ne 0) {
    $issues.Add("migration_status_after_command_failed")
  }
  if (-not $migrationStatusAfter.raw_stdout) {
    $issues.Add("migration_status_after_missing_raw_stdout")
  }
  if ($migrationStatusAfter.issue_count -gt 0 -or $migrationStatusAfter.passed -ne $true) {
    $issues.Add("migration_status_after_has_issues")
  }
  if ($migrationStatusAfter.pending_count -gt 0) {
    $issues.Add("migration_status_after_has_pending_migrations")
  }
}

if ($migrationAudit -and $migrationStatusAfter -and $null -ne $migrationAudit.latest_version) {
  if ($null -eq $migrationStatusAfter.latest_applied_version) {
    $issues.Add("migration_status_after_missing_latest_applied_version")
  } elseif ([int]$migrationStatusAfter.latest_applied_version -lt [int]$migrationAudit.latest_version) {
    $issues.Add("migration_status_after_behind_audit_latest_version")
  }
}

if ($stagingReadiness) {
  if ($stagingReadiness.gate_version -ne "staging-readiness-v3") {
    $issues.Add("unsupported_staging_readiness_version")
  }
  if ($stagingReadiness.passed -ne $true) {
    $issues.Add("staging_readiness_not_passed")
  }
  if ($stagingReadiness.issue_count -gt 0) {
    $issues.Add("staging_readiness_has_issues")
  }
}

if ($backupManifestJson) {
  if ($backupManifestJson.backup_version -ne "ielts-speaking-backup-v1") {
    $issues.Add("unsupported_backup_manifest_version")
  }
  if (-not $backupManifestJson.postgres.dump.sha256) {
    $issues.Add("backup_manifest_missing_postgres_sha256")
  }
  if (-not $backupManifestJson.minio.archive.sha256) {
    $issues.Add("backup_manifest_missing_minio_sha256")
  }
}

if ($backupIntegrity) {
  if ($backupIntegrity.evidence_version -ne "backup-integrity-evidence-v1") {
    $issues.Add("unsupported_backup_integrity_version")
  }
  if ($backupIntegrity.passed -ne $true) {
    $issues.Add("backup_integrity_not_passed")
  }
  if ($backupIntegrity.issue_count -gt 0) {
    $issues.Add("backup_integrity_has_issues")
  }
  if ($backupIntegrity.verified_file_count -lt 2) {
    $issues.Add("backup_integrity_missing_verified_files")
  }
  if ($backupManifestFile -and $backupIntegrity.manifest -and $backupIntegrity.manifest -ne $backupManifestFile.path) {
    $issues.Add("backup_integrity_manifest_path_mismatch")
  }
}

$effectiveMigrationVersion = if ($MigrationVersion) { $MigrationVersion } elseif ($migrationAudit -and $null -ne $migrationAudit.latest_version) { "v$($migrationAudit.latest_version)" } else { $null }
if (-not $effectiveMigrationVersion) {
  $issues.Add("missing_migration_version")
}

$record = [pscustomobject]@{
  generated_at = (Get-Date).ToUniversalTime().ToString("o")
  record_version = "release-record-v1"
  release_owner = $ReleaseOwner
  version_tag = $VersionTag
  migration_version = $effectiveMigrationVersion
  monitoring_window = $MonitoringWindow
  rollback = [pscustomobject]@{
    decision_owner = $RollbackDecisionOwner
    image_tag = $RollbackImageTag
    compose_env_version = $ComposeEnvVersion
    strategy = "rerun staging readiness after rollback; use forward-fix migration when down migration is unsafe"
  }
  evidence = [pscustomobject]@{
    migration_audit = [pscustomobject]@{
      file = $migrationAuditFile
      audit_version = if ($migrationAudit) { $migrationAudit.audit_version } else { $null }
      latest_version = if ($migrationAudit) { $migrationAudit.latest_version } else { $null }
      issue_count = if ($migrationAudit) { $migrationAudit.issue_count } else { $null }
      review_item_count = if ($migrationAudit) { $migrationAudit.review_item_count } else { $null }
      passed = if ($migrationAudit) { $migrationAudit.passed } else { $false }
    }
    migration_status_before = [pscustomobject]@{
      file = $migrationStatusBeforeFile
      evidence_version = if ($migrationStatusBefore) { $migrationStatusBefore.evidence_version } else { $null }
      phase = if ($migrationStatusBefore) { $migrationStatusBefore.phase } else { $null }
      command = if ($migrationStatusBefore) { $migrationStatusBefore.command } else { $null }
      exit_code = if ($migrationStatusBefore) { $migrationStatusBefore.exit_code } else { $null }
      applied_count = if ($migrationStatusBefore) { $migrationStatusBefore.applied_count } else { $null }
      pending_count = if ($migrationStatusBefore) { $migrationStatusBefore.pending_count } else { $null }
      latest_applied_version = if ($migrationStatusBefore) { $migrationStatusBefore.latest_applied_version } else { $null }
      latest_seen_version = if ($migrationStatusBefore) { $migrationStatusBefore.latest_seen_version } else { $null }
      passed = if ($migrationStatusBefore) { $migrationStatusBefore.passed } else { $false }
    }
    migration_status_after = [pscustomobject]@{
      file = $migrationStatusAfterFile
      evidence_version = if ($migrationStatusAfter) { $migrationStatusAfter.evidence_version } else { $null }
      phase = if ($migrationStatusAfter) { $migrationStatusAfter.phase } else { $null }
      command = if ($migrationStatusAfter) { $migrationStatusAfter.command } else { $null }
      exit_code = if ($migrationStatusAfter) { $migrationStatusAfter.exit_code } else { $null }
      applied_count = if ($migrationStatusAfter) { $migrationStatusAfter.applied_count } else { $null }
      pending_count = if ($migrationStatusAfter) { $migrationStatusAfter.pending_count } else { $null }
      latest_applied_version = if ($migrationStatusAfter) { $migrationStatusAfter.latest_applied_version } else { $null }
      latest_seen_version = if ($migrationStatusAfter) { $migrationStatusAfter.latest_seen_version } else { $null }
      passed = if ($migrationStatusAfter) { $migrationStatusAfter.passed } else { $false }
    }
    staging_readiness = [pscustomobject]@{
      file = $stagingReadinessFile
      gate_version = if ($stagingReadiness) { $stagingReadiness.gate_version } else { $null }
      generated_at = if ($stagingReadiness) { $stagingReadiness.generated_at } else { $null }
      issue_count = if ($stagingReadiness) { $stagingReadiness.issue_count } else { $null }
      passed = if ($stagingReadiness) { $stagingReadiness.passed } else { $false }
    }
    backup_manifest = [pscustomobject]@{
      file = $backupManifestFile
      backup_version = if ($backupManifestJson) { $backupManifestJson.backup_version } else { $null }
      generated_at = if ($backupManifestJson) { $backupManifestJson.generated_at } else { $null }
      postgres_sha256 = if ($backupManifestJson) { $backupManifestJson.postgres.dump.sha256 } else { $null }
      minio_sha256 = if ($backupManifestJson) { $backupManifestJson.minio.archive.sha256 } else { $null }
    }
    backup_integrity = [pscustomobject]@{
      file = $backupIntegrityFile
      evidence_version = if ($backupIntegrity) { $backupIntegrity.evidence_version } else { $null }
      manifest = if ($backupIntegrity) { $backupIntegrity.manifest } else { $null }
      verified_file_count = if ($backupIntegrity) { $backupIntegrity.verified_file_count } else { $null }
      issue_count = if ($backupIntegrity) { $backupIntegrity.issue_count } else { $null }
      passed = if ($backupIntegrity) { $backupIntegrity.passed } else { $false }
    }
  }
  issue_count = $issues.Count
  issues = $issues
  passed = ($issues.Count -eq 0)
}

$recordJson = $record | ConvertTo-Json -Depth 10
if ($OutputFile) {
  $outputDir = Split-Path -Parent $OutputFile
  if ($outputDir) {
    New-Item -ItemType Directory -Force -Path $outputDir | Out-Null
  }
  Set-Content -LiteralPath $OutputFile -Value $recordJson -Encoding UTF8
}
$recordJson

if ($issues.Count -gt 0) {
  exit 1
}
