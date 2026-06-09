param(
  [string]$MigrationsDir = "services/api-go/internal/db/migrations",
  [string]$OutputFile
)

$ErrorActionPreference = "Stop"

function Get-SectionText {
  param(
    [string]$Content,
    [string]$StartMarker,
    [string]$EndMarker
  )

  $start = $Content.IndexOf($StartMarker, [StringComparison]::OrdinalIgnoreCase)
  if ($start -lt 0) {
    return ""
  }
  $start += $StartMarker.Length
  if ([string]::IsNullOrEmpty($EndMarker)) {
    return $Content.Substring($start)
  }
  $end = $Content.IndexOf($EndMarker, $start, [StringComparison]::OrdinalIgnoreCase)
  if ($end -lt 0) {
    return $Content.Substring($start)
  }
  return $Content.Substring($start, $end - $start)
}

function Get-OperationMatches {
  param([string]$Sql)

  $patterns = @(
    @{ name = "drop_table"; pattern = "(?im)\bDROP\s+TABLE\b" },
    @{ name = "drop_column"; pattern = "(?im)\bDROP\s+COLUMN\b" },
    @{ name = "drop_type"; pattern = "(?im)\bDROP\s+TYPE\b" },
    @{ name = "drop_extension"; pattern = "(?im)\bDROP\s+EXTENSION\b" },
    @{ name = "truncate"; pattern = "(?im)\bTRUNCATE\b" },
    @{ name = "delete_from"; pattern = "(?im)\bDELETE\s+FROM\b" }
  )

  $matches = @()
  foreach ($entry in $patterns) {
    foreach ($match in [regex]::Matches($Sql, $entry.pattern)) {
      $line = 1 + ($Sql.Substring(0, $match.Index).ToCharArray() | Where-Object { $_ -eq "`n" }).Count
      $matches += [pscustomobject]@{
        operation = $entry.name
        line = $line
        text = $match.Value.Trim()
      }
    }
  }
  return $matches
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

$resolvedMigrationsDir = Resolve-Path -LiteralPath $MigrationsDir
$files = Get-ChildItem -LiteralPath $resolvedMigrationsDir -Filter "*.sql" | Sort-Object Name
$issues = [System.Collections.Generic.List[string]]::new()
$reviewItems = [System.Collections.Generic.List[object]]::new()
$records = [System.Collections.Generic.List[object]]::new()
$seenVersions = @{}
$expectedVersion = 1

if ($files.Count -eq 0) {
  $issues.Add("no_migration_files")
}

foreach ($file in $files) {
  $nameMatch = [regex]::Match($file.Name, "^(?<version>\d{6})_[a-z0-9_]+\.sql$")
  $version = $null
  if (-not $nameMatch.Success) {
    $issues.Add("invalid_file_name:$($file.Name)")
  } else {
    $version = [int]$nameMatch.Groups["version"].Value
    if ($seenVersions.ContainsKey($version)) {
      $issues.Add("duplicate_version:$($nameMatch.Groups["version"].Value)")
    } else {
      $seenVersions[$version] = $file.Name
    }
    if ($version -ne $expectedVersion) {
      $issues.Add("non_contiguous_version:expected_$('{0:D6}' -f $expectedVersion)_got_$('{0:D6}' -f $version)")
      $expectedVersion = $version
    }
    $expectedVersion += 1
  }

  $content = Get-Content -Raw -LiteralPath $file.FullName
  $hasUp = $content.IndexOf("-- +goose Up", [StringComparison]::OrdinalIgnoreCase) -ge 0
  $hasDown = $content.IndexOf("-- +goose Down", [StringComparison]::OrdinalIgnoreCase) -ge 0
  if (-not $hasUp) {
    $issues.Add("missing_goose_up:$($file.Name)")
  }
  if (-not $hasDown) {
    $issues.Add("missing_goose_down:$($file.Name)")
  }

  $upSql = Get-SectionText -Content $content -StartMarker "-- +goose Up" -EndMarker "-- +goose Down"
  $downSql = Get-SectionText -Content $content -StartMarker "-- +goose Down" -EndMarker ""
  $upDestructive = @(Get-OperationMatches -Sql $upSql)
  $downDestructive = @(Get-OperationMatches -Sql $downSql)
  if ($upDestructive.Count -gt 0) {
    $reviewItems.Add([pscustomobject]@{
      file = $file.Name
      reason = "destructive_up_sql_requires_release_review"
      operations = $upDestructive
    })
  }

  $records.Add([pscustomobject]@{
    file = $file.Name
    version = $version
    bytes = $file.Length
    sha256 = Get-Sha256Hex -Path $file.FullName
    has_goose_up = $hasUp
    has_goose_down = $hasDown
    destructive_up_operation_count = $upDestructive.Count
    destructive_down_operation_count = $downDestructive.Count
  })
}

$summary = [pscustomobject]@{
  generated_at = (Get-Date).ToUniversalTime().ToString("o")
  audit_version = "migration-audit-v1"
  migrations_dir = $resolvedMigrationsDir.Path
  migration_count = $files.Count
  latest_version = if ($records.Count -gt 0) { ($records | Sort-Object version -Descending | Select-Object -First 1).version } else { $null }
  issue_count = $issues.Count
  issues = $issues
  review_item_count = $reviewItems.Count
  review_items = $reviewItems
  migrations = $records
  passed = ($issues.Count -eq 0)
}

$summaryJson = $summary | ConvertTo-Json -Depth 10
if ($OutputFile) {
  $outputDir = Split-Path -Parent $OutputFile
  if ($outputDir) {
    New-Item -ItemType Directory -Force -Path $outputDir | Out-Null
  }
  Set-Content -LiteralPath $OutputFile -Value $summaryJson -Encoding UTF8
}
$summaryJson

if ($issues.Count -gt 0) {
  exit 1
}
