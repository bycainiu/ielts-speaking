param(
    [string]$EnvFile = ".env.staging",
    [string]$OutputFile,
    [switch]$AllowExamplePlaceholders,
    [switch]$SkipRemoteChecks
)

$ErrorActionPreference = "Stop"

function Read-DotEnvFile {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) {
        throw "Env file not found: $Path"
    }
    $values = @{}
    foreach ($line in Get-Content -LiteralPath $Path) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith("#")) {
            continue
        }
        $parts = $trimmed.Split("=", 2)
        if ($parts.Count -ne 2) {
            continue
        }
        $values[$parts[0].Trim()] = $parts[1].Trim()
    }
    return $values
}

function Test-PlaceholderValue {
    param([string]$Value)
    if (-not $Value) {
        return $true
    }
    $lower = $Value.ToLowerInvariant()
    return $lower.Contains("change-me") -or $lower.Contains("replace-with") -or $lower.Contains("example.com")
}

function Require-EnvValue {
    param(
        [hashtable]$Values,
        [string]$Name,
        [System.Collections.Generic.List[string]]$Issues
    )
    if (-not $Values.ContainsKey($Name) -or -not $Values[$Name]) {
        $Issues.Add("missing:$Name")
        return
    }
    if (-not $AllowExamplePlaceholders -and (Test-PlaceholderValue -Value $Values[$Name])) {
        $Issues.Add("placeholder:$Name")
    }
}

function Require-HttpsUrl {
    param(
        [hashtable]$Values,
        [string]$Name,
        [System.Collections.Generic.List[string]]$Issues
    )
    if ($Values.ContainsKey($Name) -and $Values[$Name] -and -not $Values[$Name].StartsWith("https://")) {
        $Issues.Add("https_required:$Name")
    }
}

function Invoke-HealthCheck {
    param(
        [string]$Name,
        [string]$Url,
        [System.Collections.Generic.List[object]]$Checks,
        [System.Collections.Generic.List[string]]$Issues
    )
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 15
        $Checks.Add([PSCustomObject]@{
            name = $Name
            url = $Url
            status_code = $response.StatusCode
            passed = ($response.StatusCode -ge 200 -and $response.StatusCode -lt 400)
        })
        if ($response.StatusCode -lt 200 -or $response.StatusCode -ge 400) {
            $Issues.Add("remote_check_failed:${Name}:$($response.StatusCode)")
        }
    } catch {
        $Checks.Add([PSCustomObject]@{
            name = $Name
            url = $Url
            status_code = 0
            passed = $false
            error = $_.Exception.Message
        })
        $Issues.Add("remote_check_failed:${Name}")
    }
}

function Get-ForbiddenBandFields {
    param([object]$Value)
    $forbidden = [System.Collections.Generic.List[string]]::new()
    Add-ForbiddenBandFields -Value $Value -Path "" -Forbidden $forbidden
    return ,$forbidden
}

function Add-ForbiddenBandFields {
    param(
        [object]$Value,
        [string]$Path,
        [System.Collections.Generic.List[string]]$Forbidden
    )
    if ($null -eq $Value) {
        return
    }
    if ($Value -is [System.Collections.IEnumerable] -and -not ($Value -is [string]) -and -not ($Value -is [pscustomobject])) {
        $index = 0
        foreach ($item in $Value) {
            $itemPath = if ($Path) { "${Path}[$index]" } else { "[$index]" }
            Add-ForbiddenBandFields -Value $item -Path $itemPath -Forbidden $Forbidden
            $index += 1
        }
        return
    }
    if ($Value -is [pscustomobject]) {
        foreach ($property in $Value.PSObject.Properties) {
            $propertyPath = if ($Path) { "$Path.$($property.Name)" } else { $property.Name }
            if ($property.Name -in @("overall_band", "predicted_band", "band")) {
                $Forbidden.Add($propertyPath)
            }
            Add-ForbiddenBandFields -Value $property.Value -Path $propertyPath -Forbidden $Forbidden
        }
    }
}

function Invoke-SpeechTimestampSmoke {
    param(
        [string]$BaseUrl,
        [System.Collections.Generic.List[object]]$Checks,
        [System.Collections.Generic.List[string]]$Issues
    )
    $url = "$($BaseUrl.TrimEnd('/'))/speech/transcribe-timestamps"
    $payload = @{
        audio_asset_id = "staging_readiness_timestamp_smoke"
        provider = "deterministic"
        language_hint = "en"
        duration_ms = 4800
        expected_transcript = "Technology helps students learn faster."
        metadata = @{
            source = "staging_readiness_gate"
        }
    }
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Method Post -Uri $url -ContentType "application/json" -Body ($payload | ConvertTo-Json -Depth 8) -TimeoutSec 20
        $body = $response.Content | ConvertFrom-Json
        $wordCount = @($body.word_timestamps).Count
        $passed = ($response.StatusCode -ge 200 -and $response.StatusCode -lt 400 -and $wordCount -gt 0 -and $body.downstream_confidence -ge 0)
        $Checks.Add([PSCustomObject]@{
            name = "speech_transcribe_timestamps"
            url = $url
            status_code = $response.StatusCode
            word_timestamp_count = $wordCount
            downstream_confidence = $body.downstream_confidence
            passed = $passed
        })
        if (-not $passed) {
            $Issues.Add("remote_check_failed:speech_transcribe_timestamps")
        }
    } catch {
        $Checks.Add([PSCustomObject]@{
            name = "speech_transcribe_timestamps"
            url = $url
            status_code = 0
            passed = $false
            error = $_.Exception.Message
        })
        $Issues.Add("remote_check_failed:speech_transcribe_timestamps")
    }
}

function Invoke-SpeechAssessPolicySmoke {
    param(
        [string]$BaseUrl,
        [System.Collections.Generic.List[object]]$Checks,
        [System.Collections.Generic.List[string]]$Issues
    )
    $url = "$($BaseUrl.TrimEnd('/'))/speech/assess"
    $payload = @{
        audio_asset_id = "staging_readiness_assess_smoke"
        session_id = "staging_readiness_session"
        turn_id = "staging_readiness_turn"
        mode = "mock_exam"
        duration_ms = 12000
        transcript = "Um I think public transport is useful because it is cheaper and cleaner."
        word_timestamps = @(
            @{ word = "Um"; start_ms = 100; end_ms = 250; confidence = 0.72 },
            @{ word = "I"; start_ms = 300; end_ms = 360; confidence = 0.88 },
            @{ word = "think"; start_ms = 900; end_ms = 1200; confidence = 0.9 }
        )
        vad_segments = @(
            @{ start_ms = 100; end_ms = 250; speech_probability = 0.85 },
            @{ start_ms = 300; end_ms = 1200; speech_probability = 0.9 }
        )
        metadata = @{
            source = "staging_readiness_gate"
        }
    }
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Method Post -Uri $url -ContentType "application/json" -Body ($payload | ConvertTo-Json -Depth 8) -TimeoutSec 20
        $body = $response.Content | ConvertFrom-Json
        $forbiddenFields = Get-ForbiddenBandFields -Value $body
        $policyPassed = ($body.policy.ielts_band_output_allowed -eq $false)
        $evidencePassed = [bool]$body.evidence_id -and [bool]$body.audio_quality -and [bool]$body.fluency -and [bool]$body.pronunciation
        $passed = ($response.StatusCode -ge 200 -and $response.StatusCode -lt 400 -and $policyPassed -and $evidencePassed -and $forbiddenFields.Count -eq 0)
        $Checks.Add([PSCustomObject]@{
            name = "speech_assess_policy"
            url = $url
            status_code = $response.StatusCode
            ielts_band_output_allowed = $body.policy.ielts_band_output_allowed
            forbidden_band_fields = $forbiddenFields
            passed = $passed
        })
        if (-not $policyPassed) {
            $Issues.Add("speech_assess_policy_failed")
        }
        if ($forbiddenFields.Count -gt 0) {
            $Issues.Add("speech_assess_direct_band_field")
        }
        if (-not $evidencePassed -or $response.StatusCode -lt 200 -or $response.StatusCode -ge 400) {
            $Issues.Add("remote_check_failed:speech_assess_policy")
        }
    } catch {
        $Checks.Add([PSCustomObject]@{
            name = "speech_assess_policy"
            url = $url
            status_code = 0
            passed = $false
            error = $_.Exception.Message
        })
        $Issues.Add("remote_check_failed:speech_assess_policy")
    }
}

function Invoke-AgentObservabilitySmoke {
    param(
        [string]$BaseUrl,
        [System.Collections.Generic.List[object]]$Checks,
        [System.Collections.Generic.List[string]]$Issues
    )
    $summaryUrl = "$($BaseUrl.TrimEnd('/'))/agent/observability/summary?limit=20"
    $alertsUrl = "$($BaseUrl.TrimEnd('/'))/agent/observability/alerts?limit=20"
    try {
        $summaryResponse = Invoke-WebRequest -UseBasicParsing -Uri $summaryUrl -TimeoutSec 20
        $summary = $summaryResponse.Content | ConvertFrom-Json
        $alertsResponse = Invoke-WebRequest -UseBasicParsing -Uri $alertsUrl -TimeoutSec 20
        $alerts = $alertsResponse.Content | ConvertFrom-Json
        $hasSummaryFields = $null -ne $summary.run_count -and $null -ne $summary.error_rate -and $null -ne $summary.structured_output_validity_rate
        $criticalAlerts = @($alerts | Where-Object { $_.severity -eq "critical" })
        $passed = (
            $summaryResponse.StatusCode -ge 200 -and $summaryResponse.StatusCode -lt 400 -and
            $alertsResponse.StatusCode -ge 200 -and $alertsResponse.StatusCode -lt 400 -and
            $hasSummaryFields -and
            $criticalAlerts.Count -eq 0
        )
        $Checks.Add([PSCustomObject]@{
            name = "agent_observability"
            url = $summaryUrl
            alerts_url = $alertsUrl
            status_code = $summaryResponse.StatusCode
            alerts_status_code = $alertsResponse.StatusCode
            run_count = $summary.run_count
            error_rate = $summary.error_rate
            structured_output_validity_rate = $summary.structured_output_validity_rate
            critical_alert_count = $criticalAlerts.Count
            passed = $passed
        })
        if (-not $hasSummaryFields) {
            $Issues.Add("agent_observability_summary_invalid")
        }
        if ($criticalAlerts.Count -gt 0) {
            $Issues.Add("agent_observability_critical_alerts")
        }
        if ($summaryResponse.StatusCode -lt 200 -or $summaryResponse.StatusCode -ge 400 -or $alertsResponse.StatusCode -lt 200 -or $alertsResponse.StatusCode -ge 400) {
            $Issues.Add("remote_check_failed:agent_observability")
        }
    } catch {
        $Checks.Add([PSCustomObject]@{
            name = "agent_observability"
            url = $summaryUrl
            alerts_url = $alertsUrl
            status_code = 0
            passed = $false
            error = $_.Exception.Message
        })
        $Issues.Add("remote_check_failed:agent_observability")
    }
}

function Invoke-AgentQualityGateSmoke {
    param(
        [string]$BaseUrl,
        [System.Collections.Generic.List[object]]$Checks,
        [System.Collections.Generic.List[string]]$Issues
    )
    $url = "$($BaseUrl.TrimEnd('/'))/agent/calibration/quality-gate"
    $payload = @{
        include_deepeval_regression = $true
        include_ragas_rag = $true
        include_promptfoo_redteam = $true
        include_performance_baseline = $true
        include_speech_calibration_contract = $true
        include_multipa_contract = $true
    }
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Method Post -Uri $url -ContentType "application/json" -Body ($payload | ConvertTo-Json -Depth 8) -TimeoutSec 30
        $body = $response.Content | ConvertFrom-Json
        $checks = @($body.checks)
        $blockedChecks = @($checks | Where-Object { $_.block_release -eq $true -or $_.status -eq "blocked" })
        $passed = ($response.StatusCode -ge 200 -and $response.StatusCode -lt 400 -and $body.status -ne "blocked" -and $blockedChecks.Count -eq 0)
        $Checks.Add([PSCustomObject]@{
            name = "agent_quality_gate"
            url = $url
            status_code = $response.StatusCode
            gate_status = $body.status
            check_count = $checks.Count
            blocked_check_count = $blockedChecks.Count
            passed = $passed
        })
        if ($body.status -eq "blocked" -or $blockedChecks.Count -gt 0) {
            $Issues.Add("agent_quality_gate_blocked")
        }
        if ($response.StatusCode -lt 200 -or $response.StatusCode -ge 400) {
            $Issues.Add("remote_check_failed:agent_quality_gate")
        }
    } catch {
        $Checks.Add([PSCustomObject]@{
            name = "agent_quality_gate"
            url = $url
            status_code = 0
            passed = $false
            error = $_.Exception.Message
        })
        $Issues.Add("remote_check_failed:agent_quality_gate")
    }
}

$resolvedEnvFile = Resolve-Path -LiteralPath $EnvFile
$envValues = Read-DotEnvFile -Path $resolvedEnvFile
$issues = [System.Collections.Generic.List[string]]::new()
$remoteChecks = [System.Collections.Generic.List[object]]::new()

$requiredNames = @(
    "APP_ENV",
    "STAGING_WEB_URL",
    "NEXT_PUBLIC_API_BASE_URL",
    "S3_PUBLIC_ENDPOINT",
    "JWT_SECRET",
    "TRACE_USER_HASH_SALT",
    "MIMO_API_KEY",
    "MIMO_BASE_URL",
    "LANGFUSE_ENABLED",
    "LANGFUSE_PUBLIC_KEY",
    "LANGFUSE_SECRET_KEY",
    "LANGFUSE_HOST",
    "AGENT_HARNESS_PUBLIC_URL",
    "SPEECH_ASSESSMENT_PUBLIC_URL",
    "POSTGRES_PASSWORD",
    "MINIO_ROOT_USER",
    "MINIO_ROOT_PASSWORD",
    "SPEECH_ASSESSMENT_URL"
)

foreach ($name in $requiredNames) {
    Require-EnvValue -Values $envValues -Name $name -Issues $issues
}

foreach ($name in @(
    "STAGING_WEB_URL",
    "NEXT_PUBLIC_API_BASE_URL",
    "S3_PUBLIC_ENDPOINT",
    "LANGFUSE_HOST",
    "AGENT_HARNESS_PUBLIC_URL",
    "SPEECH_ASSESSMENT_PUBLIC_URL"
)) {
    Require-HttpsUrl -Values $envValues -Name $name -Issues $issues
}

if ($envValues.ContainsKey("APP_ENV") -and $envValues["APP_ENV"] -ne "staging") {
    $issues.Add("app_env_must_be_staging")
}

if ($envValues.ContainsKey("LANGFUSE_ENABLED") -and $envValues["LANGFUSE_ENABLED"].ToLowerInvariant() -ne "true") {
    $issues.Add("langfuse_enabled_must_be_true")
}

docker compose --env-file $resolvedEnvFile -f docker-compose.yml -f docker-compose.staging.yml config --quiet

if (-not $SkipRemoteChecks) {
    if ($envValues["STAGING_WEB_URL"]) {
        Invoke-HealthCheck -Name "web" -Url $envValues["STAGING_WEB_URL"] -Checks $remoteChecks -Issues $issues
    }
    if ($envValues["NEXT_PUBLIC_API_BASE_URL"]) {
        $apiBase = $envValues["NEXT_PUBLIC_API_BASE_URL"].TrimEnd("/")
        Invoke-HealthCheck -Name "api_healthz" -Url "$apiBase/healthz" -Checks $remoteChecks -Issues $issues
        Invoke-HealthCheck -Name "api_readyz" -Url "$apiBase/readyz" -Checks $remoteChecks -Issues $issues
    }
    if ($envValues.ContainsKey("AGENT_HARNESS_PUBLIC_URL") -and $envValues["AGENT_HARNESS_PUBLIC_URL"]) {
        $agentBase = $envValues["AGENT_HARNESS_PUBLIC_URL"].TrimEnd("/")
        Invoke-HealthCheck -Name "agent_healthz" -Url "$agentBase/healthz" -Checks $remoteChecks -Issues $issues
        Invoke-HealthCheck -Name "agent_metrics" -Url "$agentBase/metrics" -Checks $remoteChecks -Issues $issues
        Invoke-AgentObservabilitySmoke -BaseUrl $agentBase -Checks $remoteChecks -Issues $issues
        Invoke-AgentQualityGateSmoke -BaseUrl $agentBase -Checks $remoteChecks -Issues $issues
    }
    if ($envValues.ContainsKey("SPEECH_ASSESSMENT_PUBLIC_URL") -and $envValues["SPEECH_ASSESSMENT_PUBLIC_URL"]) {
        $speechBase = $envValues["SPEECH_ASSESSMENT_PUBLIC_URL"].TrimEnd("/")
        Invoke-HealthCheck -Name "speech_healthz" -Url "$speechBase/healthz" -Checks $remoteChecks -Issues $issues
        Invoke-HealthCheck -Name "speech_metrics" -Url "$speechBase/metrics" -Checks $remoteChecks -Issues $issues
        Invoke-SpeechTimestampSmoke -BaseUrl $speechBase -Checks $remoteChecks -Issues $issues
        Invoke-SpeechAssessPolicySmoke -BaseUrl $speechBase -Checks $remoteChecks -Issues $issues
    }
    if ($envValues["LANGFUSE_HOST"]) {
        $langfuseBase = $envValues["LANGFUSE_HOST"].TrimEnd("/")
        Invoke-HealthCheck -Name "langfuse" -Url $langfuseBase -Checks $remoteChecks -Issues $issues
    }
}

$summary = [PSCustomObject]@{
    generated_at = (Get-Date).ToUniversalTime().ToString("o")
    gate_version = "staging-readiness-v3"
    env_file = $resolvedEnvFile.Path
    allow_example_placeholders = [bool]$AllowExamplePlaceholders
    skip_remote_checks = [bool]$SkipRemoteChecks
    compose_config_passed = $true
    remote_checks = $remoteChecks
    issue_count = $issues.Count
    issues = $issues
    passed = ($issues.Count -eq 0)
}

$summaryJson = $summary | ConvertTo-Json -Depth 8
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
