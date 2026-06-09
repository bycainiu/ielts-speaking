param(
  [Parameter(Mandatory = $true)]
  [string]$BackupDir,
  [Parameter(Mandatory = $true)]
  [string]$Confirmation,
  [string]$PostgresUser = "ielts",
  [string]$PostgresDb = "ielts_speaking",
  [string]$MinioAlias = "local",
  [string]$MinioBucket = "ielts-speaking-local",
  [string]$MinioRootUser = "minioadmin",
  [string]$MinioRootPassword = "minioadmin",
  [switch]$AllowMissingManifest
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

function Assert-BackupFileMatchesManifest {
  param(
    [Parameter(Mandatory = $true)]
    [string]$Path,
    [Parameter(Mandatory = $true)]
    [object]$Record,
    [Parameter(Mandatory = $true)]
    [string]$Role
  )

  if (-not (Test-Path -LiteralPath $Path)) {
    throw "Missing $Role file: $Path"
  }

  $resolvedPath = Resolve-Path -LiteralPath $Path
  $item = Get-Item -LiteralPath $resolvedPath
  if ($null -ne $Record.bytes -and [int64]$Record.bytes -ne [int64]$item.Length) {
    throw "$Role size mismatch. Expected $($Record.bytes), got $($item.Length)."
  }

  $actualHash = Get-Sha256Hex -Path $resolvedPath.Path
  if ($Record.sha256 -and $Record.sha256.ToLowerInvariant() -ne $actualHash) {
    throw "$Role checksum mismatch. Expected $($Record.sha256), got $actualHash."
  }

  [pscustomobject]@{
    role = $Role
    path = $resolvedPath.Path
    bytes = $item.Length
    sha256 = $actualHash
    verified = $true
  }
}

if ($Confirmation -ne "RESTORE_STAGING_DATA") {
  throw "Refusing restore. Pass -Confirmation RESTORE_STAGING_DATA after verifying the target environment."
}

$resolvedBackupDir = Resolve-Path $BackupDir
$pgLocalPath = Join-Path $resolvedBackupDir.Path "postgres.dump"
$minioLocalPath = Join-Path $resolvedBackupDir.Path "minio.tgz"
$manifestPath = Join-Path $resolvedBackupDir.Path "manifest.json"
$manifest = $null
$verifiedFiles = @()
$warnings = @()

if (-not (Test-Path $pgLocalPath)) {
  throw "Missing postgres.dump in $resolvedBackupDir"
}
if (-not (Test-Path $minioLocalPath)) {
  throw "Missing minio.tgz in $resolvedBackupDir"
}

if (Test-Path -LiteralPath $manifestPath) {
  $manifest = Get-Content -Raw -LiteralPath $manifestPath | ConvertFrom-Json
  if ($manifest.backup_version -ne "ielts-speaking-backup-v1") {
    throw "Unsupported backup manifest version: $($manifest.backup_version)"
  }
  $verifiedFiles += Assert-BackupFileMatchesManifest -Path $pgLocalPath -Record $manifest.postgres.dump -Role "postgres_dump"
  $verifiedFiles += Assert-BackupFileMatchesManifest -Path $minioLocalPath -Record $manifest.minio.archive -Role "minio_archive"
} elseif (-not $AllowMissingManifest) {
  throw "Missing manifest.json in $($resolvedBackupDir.Path). Pass -AllowMissingManifest only for legacy backups after manual checksum review."
} else {
  $warnings += "manifest_missing_legacy_backup"
}

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$pgContainerPath = "/tmp/ielts-speaking-restore-$timestamp.dump"
$minioContainerArchive = "/tmp/ielts-speaking-restore-$timestamp.tgz"
$minioContainerDir = "/tmp/ielts-speaking-restore-$timestamp"

docker compose cp $pgLocalPath "postgres:$pgContainerPath"
docker compose exec -T postgres pg_restore -U $PostgresUser -d $PostgresDb --clean --if-exists $pgContainerPath
docker compose exec -T postgres rm -f $pgContainerPath

docker compose cp $minioLocalPath "minio:$minioContainerArchive"
docker compose exec -T minio rm -rf $minioContainerDir
docker compose exec -T minio mkdir -p $minioContainerDir
docker compose exec -T minio tar -xzf $minioContainerArchive -C $minioContainerDir --strip-components=1
docker compose exec -T minio mc alias set $MinioAlias http://127.0.0.1:9000 $MinioRootUser $MinioRootPassword
docker compose exec -T minio mc mirror --overwrite --remove $minioContainerDir "$MinioAlias/$MinioBucket"
docker compose exec -T minio rm -rf $minioContainerDir $minioContainerArchive

[pscustomobject]@{
  restored_from = $resolvedBackupDir.Path
  manifest = if ($manifest) { (Resolve-Path -LiteralPath $manifestPath).Path } else { $null }
  verified_files = $verifiedFiles
  warnings = $warnings
  postgres = $PostgresDb
  minio_bucket = $MinioBucket
} | ConvertTo-Json -Depth 8
