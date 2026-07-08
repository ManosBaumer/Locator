# Import McDonald's deliveryinfo checkpoint JSON into the configured database.
# Usage (from repo root):
#   $env:SUPABASE_DB_PASSWORD = "your-password"
#   .\scripts\import-mcdonalds-checkpoint.ps1

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$backendDir = Join-Path $repoRoot "backend"
$checkpointDir = Join-Path $repoRoot "data\mcdonalds-checkpoint"

if (-not $env:SUPABASE_DB_PASSWORD) {
    $envFile = Join-Path $repoRoot ".env"
    if (Test-Path $envFile) {
        $line = Get-Content $envFile | Where-Object { $_ -match '^SUPABASE_DB_PASSWORD=(.+)$' } | Select-Object -First 1
        if ($line -match '^SUPABASE_DB_PASSWORD=(.+)$') {
            $env:SUPABASE_DB_PASSWORD = $Matches[1].Trim()
        }
    }
}

if (-not $env:SUPABASE_DB_PASSWORD) {
    throw "Set SUPABASE_DB_PASSWORD in .env or as an environment variable (Supabase → locater → Settings → Database)."
}

$projectRef = if ($env:SUPABASE_PROJECT_REF) { $env:SUPABASE_PROJECT_REF } else { "ycfvmdehdotogbyrpvdm" }
$password = $env:SUPABASE_DB_PASSWORD
$encoded = [uri]::EscapeDataString($password)

$env:DATABASE_URL = "postgresql+asyncpg://postgres.${projectRef}:${encoded}@aws-0-eu-west-1.pooler.supabase.com:5432/postgres"
$env:SYNC_DATABASE_URL = "postgresql+psycopg://postgres.${projectRef}:${encoded}@aws-0-eu-west-1.pooler.supabase.com:5432/postgres"
$env:ADAPTER_MCDONALDS_CHECKPOINT_DIR = $checkpointDir
$env:AMAP_API_KEY = (Get-Content (Join-Path $repoRoot ".env") | Where-Object { $_ -match '^AMAP_API_KEY=' }) -replace '^AMAP_API_KEY=', ''

Push-Location $backendDir
try {
    pip install -q .
    python -m app.ingestion.runner --chain mcdonalds_deliveryinfo --from-checkpoint
    Write-Host "Import complete."
}
finally {
    Pop-Location
}
