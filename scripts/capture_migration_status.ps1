param(
  [ValidateSet("pre", "post", "ad-hoc")]
  [string]$Phase = "ad-hoc",
  [ValidateSet("DockerCompose", "LocalGo", "RawFile", "RawText")]
  [string]$Mode = "DockerCompose",
  [string]$RawStatusFile,
  [string]$RawStatusText,
  [string]$OutputFile,
  [switch]$AllowPending
)

$ErrorActionPreference = "Stop"

function Get-StatusRows {
  param([string]$Text)

  $rows = [System.Collections.Generic.List[object]]::new()
  foreach ($line in ($Text -split "`r?`n")) {
    $match = [regex]::Match($line, "(?<file>(?<version>\d{6})_[a-z0-9_]+\.sql)", "IgnoreCase")
    if (-not $match.Success) {
      continue
    }
    $state = if ($line -match "(?i)\bpending\b") { "pending" } else { "applied" }
    $rows.Add([pscustomobject]@{
      version = [int]$match.Groups["version"].Value
      file = $match.Groups["file"].Value
      state = $state
      line = $line.Trim()
    })
  }
  return $rows.ToArray()
}

function Invoke-StatusCommand {
  param([string]$Mode)

  if ($Mode -eq "DockerCompose") {
    $output = & docker compose run --rm api-go migrate status 2>&1
    return [pscustomobject]@{
      command = "docker compose run --rm api-go migrate status"
      exit_code = $LASTEXITCODE
      output = ($output | Out-String)
    }
  }

  Push-Location "services/api-go"
  try {
    $output = & go run ./cmd/api migrate status 2>&1
    return [pscustomobject]@{
      command = "cd services/api-go && go run ./cmd/api migrate status"
      exit_code = $LASTEXITCODE
      output = ($output | Out-String)
    }
  } finally {
    Pop-Location
  }
}

$command = ""
$exitCode = 0
$rawOutput = ""

if ($Mode -eq "RawFile") {
  if (-not $RawStatusFile) {
    throw "RawStatusFile is required when Mode=RawFile"
  }
  $resolvedRawStatusFile = Resolve-Path -LiteralPath $RawStatusFile
  $command = "raw-file:$($resolvedRawStatusFile.Path)"
  $rawOutput = Get-Content -Raw -LiteralPath $resolvedRawStatusFile
} elseif ($Mode -eq "RawText") {
  if (-not $RawStatusText) {
    throw "RawStatusText is required when Mode=RawText"
  }
  $command = "raw-text"
  $rawOutput = $RawStatusText
} else {
  $result = Invoke-StatusCommand -Mode $Mode
  $command = $result.command
  $exitCode = $result.exit_code
  $rawOutput = $result.output
}

$rows = @(Get-StatusRows -Text $rawOutput)
$pendingRows = @($rows | Where-Object { $_.state -eq "pending" })
$appliedRows = @($rows | Where-Object { $_.state -eq "applied" })
$issues = [System.Collections.Generic.List[string]]::new()
$pendingAllowed = [bool]$AllowPending -or $Phase -eq "pre"

if ($exitCode -ne 0) {
  $issues.Add("migration_status_command_failed")
}
if ([string]::IsNullOrWhiteSpace($rawOutput)) {
  $issues.Add("migration_status_output_empty")
}
if ($rows.Count -eq 0) {
  $issues.Add("migration_status_rows_empty")
}
if ($pendingRows.Count -gt 0 -and -not $pendingAllowed) {
  $issues.Add("pending_migrations_present")
}

$evidence = [pscustomobject]@{
  generated_at = (Get-Date).ToUniversalTime().ToString("o")
  evidence_version = "migration-status-evidence-v1"
  phase = $Phase
  command = $command
  exit_code = $exitCode
  pending_allowed = $pendingAllowed
  migration_count = $rows.Count
  applied_count = $appliedRows.Count
  pending_count = $pendingRows.Count
  latest_seen_version = if ($rows.Count -gt 0) { ($rows | Sort-Object version -Descending | Select-Object -First 1).version } else { $null }
  latest_applied_version = if ($appliedRows.Count -gt 0) { ($appliedRows | Sort-Object version -Descending | Select-Object -First 1).version } else { $null }
  rows = $rows
  issue_count = $issues.Count
  issues = $issues
  passed = ($issues.Count -eq 0)
  raw_stdout = $rawOutput.Trim()
}

$json = $evidence | ConvertTo-Json -Depth 10
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
