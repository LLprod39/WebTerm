param(
    [string]$ProjectName = "webtrerm-prod-multi-user-smoke",
    [int]$Users = 4,
    [int]$TerminalSessionsPerUser = 2,
    [int]$PipelineRunsPerUser = 2,
    [int]$AgentRunsPerUser = 0,
    [switch]$KeepUp
)

$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $true

$root = "C:\WebTrerm"
$envFile = Join-Path $root ".env.production.example"
$smokeEnvFile = Join-Path $root ".env.production.multi-user.smoke.tmp"
$composeMain = Join-Path $root "docker-compose.production.yml"
$composeSmoke = Join-Path $root "docker-compose.production.smoke.yml"
$resultsFile = Join-Path $root "docker\\multi-user-load-smoke.results.json"
$statsFile = Join-Path $root "docker\\multi-user-load-smoke.stats.txt"
$seedFile = Join-Path $root "docker\\multi-user-load-smoke.seed.json"
$backendContainer = "mini-prod-backend-smoke"
$sshTargetContainer = "mini-prod-ssh-target-smoke"

function Wait-HttpOk {
    param(
        [string]$Url,
        [int]$TimeoutSeconds = 180
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 10
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 300) {
                return $response
            }
        } catch {
            Start-Sleep -Seconds 2
            continue
        }
        Start-Sleep -Seconds 2
    }

    throw "Timed out waiting for HTTP success: $Url"
}

function Wait-ContainerHealthy {
    param(
        [string]$ContainerName,
        [int]$TimeoutSeconds = 180
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $health = docker inspect --format "{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}" $ContainerName
            if (($health | Out-String).Trim() -eq "healthy") {
                return
            }
        } catch {
        }
        Start-Sleep -Seconds 2
    }

    throw "Timed out waiting for healthy container: $ContainerName"
}

function Invoke-Compose {
    param([string[]]$ComposeArgs)
    & docker compose --project-name $ProjectName --env-file $smokeEnvFile -f $composeMain -f $composeSmoke @ComposeArgs
}

function Assert-LastExitCode {
    param([string]$Message)
    if ($LASTEXITCODE -ne 0) {
        throw "$Message (exit code $LASTEXITCODE)"
    }
}

function Write-SmokeEnvFile {
    Copy-Item $envFile $smokeEnvFile -Force
    Add-Content -Path $smokeEnvFile -Value @(
        "",
        "FRONTEND_PORT=18080",
        "DJANGO_HOST_PORT=19000",
        "POSTGRES_HOST_PORT=15432",
        "REDIS_HOST_PORT=16379",
        "SITE_URL=http://127.0.0.1:18080",
        "FRONTEND_APP_URL=http://127.0.0.1:18080",
        "ALLOWED_HOSTS=127.0.0.1,localhost,nginx,backend",
        "CSRF_TRUSTED_ORIGINS=http://127.0.0.1:18080,http://localhost:18080,http://nginx:8080,http://backend:9000",
        "SECURE_SSL_REDIRECT=false",
        "SESSION_COOKIE_SECURE=false",
        "CSRF_COOKIE_SECURE=false",
        "SECURE_HSTS_SECONDS=0",
        "SECURE_HSTS_INCLUDE_SUBDOMAINS=false",
        "SECURE_HSTS_PRELOAD=false",
        "SMOKE_SSH_USERNAME=smoke",
        "SMOKE_SSH_PASSWORD=smoke-password"
    )
}

try {
    Write-SmokeEnvFile
    Invoke-Compose -ComposeArgs @("up", "-d", "--build")

    Wait-ContainerHealthy -ContainerName $sshTargetContainer
    Wait-HttpOk -Url "http://127.0.0.1:18080/nginx-health" | Out-Null
    Wait-HttpOk -Url "http://127.0.0.1:18080/api/health/" | Out-Null

    & docker exec $backendContainer sh -lc "python manage.py seed_multi_user_smoke --users $Users --password 'SmokePass123!' --ssh-host ssh-target --ssh-port 2222 --ssh-username smoke --ssh-password smoke-password --json > /tmp/multi-user-load-seed.json"
    Assert-LastExitCode -Message "Failed to seed multi-user smoke data"
    & docker cp "${backendContainer}:/tmp/multi-user-load-seed.json" $seedFile | Out-Null
    Assert-LastExitCode -Message "Failed to copy multi-user seed file"

    & docker exec $backendContainer python docker/multi_user_load_smoke.py --base-url http://nginx:8080 --seed-file /tmp/multi-user-load-seed.json --users $Users --terminal-sessions-per-user $TerminalSessionsPerUser --pipeline-runs-per-user $PipelineRunsPerUser --agent-runs-per-user $AgentRunsPerUser | Tee-Object -FilePath $resultsFile
    Assert-LastExitCode -Message "Multi-user load harness failed"

    & docker stats --no-stream $sshTargetContainer mini-prod-postgres-smoke mini-prod-redis-smoke $backendContainer mini-prod-frontend-smoke mini-prod-nginx-smoke | Tee-Object -FilePath $statsFile
    Assert-LastExitCode -Message "Failed to capture docker stats"

    Write-Output "Multi-user smoke completed. Results: $resultsFile"
    Write-Output "Resource snapshot saved: $statsFile"
} catch {
    Write-Warning $_.Exception.Message
    try {
        Invoke-Compose -ComposeArgs @("ps")
        Invoke-Compose -ComposeArgs @("logs", "--tail", "160")
    } catch {
        Write-Warning "Failed to collect compose diagnostics: $($_.Exception.Message)"
    }
    throw
} finally {
    if (-not $KeepUp) {
        try {
            Invoke-Compose -ComposeArgs @("down", "-v")
        } catch {
            Write-Warning "Failed to bring multi-user smoke stack down cleanly: $($_.Exception.Message)"
        }
    }
    if (Test-Path $smokeEnvFile) {
        Remove-Item $smokeEnvFile -Force -ErrorAction SilentlyContinue
    }
}
