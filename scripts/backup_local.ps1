param(
  [string]$BackupRoot = "tmp/backups",
  [string]$PostgresUser = "ielts",
  [string]$PostgresDb = "ielts_speaking",
  [string]$MinioAlias = "local",
  [string]$MinioBucket = "ielts-speaking-local",
  [string]$MinioRootUser = "minioadmin",
  [string]$MinioRootPassword = "minioadmin"
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

function Get-BackupFileRecord {
  param(
    [Parameter(Mandatory = $true)]
    [string]$Path,
    [Parameter(Mandatory = $true)]
    [string]$Role
  )

  $resolvedPath = Resolve-Path -LiteralPath $Path
  $item = Get-Item -LiteralPath $resolvedPath

  [pscustomobject]@{
    role = $Role
    path = $resolvedPath.Path
    file_name = $item.Name
    bytes = $item.Length
    sha256 = Get-Sha256Hex -Path $resolvedPath.Path
  }
}

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupDir = Join-Path $BackupRoot $timestamp
New-Item -ItemType Directory -Force -Path $backupDir | Out-Null

$pgContainerPath = "/tmp/ielts-speaking-$timestamp.dump"
$pgLocalPath = Join-Path $backupDir "postgres.dump"

docker compose exec -T postgres pg_dump -U $PostgresUser -d $PostgresDb -Fc --file=$pgContainerPath
docker compose cp "postgres:$pgContainerPath" $pgLocalPath
docker compose exec -T postgres rm -f $pgContainerPath

$minioContainerDir = "/tmp/ielts-speaking-minio-$timestamp"
$minioContainerArchive = "/tmp/ielts-speaking-minio-$timestamp.tgz"
$minioLocalPath = Join-Path $backupDir "minio.tgz"

docker compose exec -T minio mc alias set $MinioAlias http://127.0.0.1:9000 $MinioRootUser $MinioRootPassword
docker compose exec -T minio rm -r --force $minioContainerDir
docker compose exec -T minio mkdir -p $minioContainerDir
docker compose exec -T minio mc mirror "$MinioAlias/$MinioBucket" $minioContainerDir
docker compose exec -T minio tar -czf $minioContainerArchive -C /tmp "ielts-speaking-minio-$timestamp"
docker compose cp "minio:$minioContainerArchive" $minioLocalPath
docker compose exec -T minio rm -rf $minioContainerDir $minioContainerArchive

$postgresRecord = Get-BackupFileRecord -Path $pgLocalPath -Role "postgres_dump"
$minioRecord = Get-BackupFileRecord -Path $minioLocalPath -Role "minio_archive"
$manifestPath = Join-Path $backupDir "manifest.json"
$manifest = [pscustomobject]@{
  generated_at = (Get-Date).ToUniversalTime().ToString("o")
  backup_version = "ielts-speaking-backup-v1"
  backup_dir = (Resolve-Path $backupDir).Path
  postgres = [pscustomobject]@{
    user = $PostgresUser
    database = $PostgresDb
    dump = $postgresRecord
  }
  minio = [pscustomobject]@{
    alias = $MinioAlias
    bucket = $MinioBucket
    archive = $minioRecord
  }
}
$manifestJson = $manifest | ConvertTo-Json -Depth 8
Set-Content -LiteralPath $manifestPath -Value $manifestJson -Encoding UTF8

[pscustomobject]@{
  backup_dir = (Resolve-Path $backupDir).Path
  manifest = (Resolve-Path $manifestPath).Path
  postgres_dump = $postgresRecord
  minio_archive = $minioRecord
} | ConvertTo-Json -Depth 8
