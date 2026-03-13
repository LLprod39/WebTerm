param(
    [string]$ProjectName = "webtrerm-prod-smoke",
    [switch]$KeepUp
)

$ErrorActionPreference = "Stop"

$root = "C:\WebTrerm"
$envFile = Join-Path $root ".env.production.example"
$smokeEnvFile = Join-Path $root ".env.production.smoke.tmp"
$composeMain = Join-Path $root "docker-compose.production.yml"
$composeSmoke = Join-Path $root "docker-compose.production.smoke.yml"

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

function Invoke-Compose {
    param([string[]]$ComposeArgs)
    & docker compose --project-name $ProjectName --env-file $smokeEnvFile -f $composeMain -f $composeSmoke @ComposeArgs
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
        "ALLOWED_HOSTS=127.0.0.1,localhost",
        "CSRF_TRUSTED_ORIGINS=http://127.0.0.1:18080,http://localhost:18080",
        "SECURE_SSL_REDIRECT=false",
        "SESSION_COOKIE_SECURE=false",
        "CSRF_COOKIE_SECURE=false",
        "SECURE_HSTS_SECONDS=0",
        "SECURE_HSTS_INCLUDE_SUBDOMAINS=false",
        "SECURE_HSTS_PRELOAD=false"
    )
}

try {
    Write-SmokeEnvFile
    Invoke-Compose -ComposeArgs @("up", "-d", "--build")

    Wait-HttpOk -Url "http://127.0.0.1:18080/nginx-health" | Out-Null
    Wait-HttpOk -Url "http://127.0.0.1:18080/api/health/" | Out-Null
    Wait-HttpOk -Url "http://127.0.0.1:18080/" | Out-Null
    Wait-HttpOk -Url "http://127.0.0.1:18080/static/admin/css/base.css" | Out-Null

    & docker exec "mini-prod-backend-smoke" sh -lc "mkdir -p /workspace/media && printf 'prod-smoke-ok' > /workspace/media/prod-smoke.txt" | Out-Null
    $media = Wait-HttpOk -Url "http://127.0.0.1:18080/media/prod-smoke.txt"
    if (($media.Content | Out-String).Trim() -ne "prod-smoke-ok") {
        throw "Media smoke check returned unexpected content"
    }

    Write-Output "Production smoke stack is healthy on http://127.0.0.1:18080"
} catch {
    Write-Warning $_.Exception.Message
    try {
        Invoke-Compose -ComposeArgs @("ps")
        Invoke-Compose -ComposeArgs @("logs", "--tail", "120")
    } catch {
        Write-Warning "Failed to collect compose diagnostics: $($_.Exception.Message)"
    }
    throw
} finally {
    if (-not $KeepUp) {
        try {
            Invoke-Compose -ComposeArgs @("down", "-v")
        } catch {
            Write-Warning "Failed to bring smoke stack down cleanly: $($_.Exception.Message)"
        }
    }
    if (Test-Path $smokeEnvFile) {
        Remove-Item $smokeEnvFile -Force -ErrorAction SilentlyContinue
    }
}
