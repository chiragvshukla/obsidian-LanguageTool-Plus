# Full local check: lint, format, types, tests. Run from anywhere.
$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$gateway = Join-Path $PSScriptRoot "../gateway"
Push-Location $gateway
try {
    if ($env:CI) { uv sync --frozen } else { uv sync }
    if ($LASTEXITCODE -ne 0) { throw "uv sync failed" }

    uv run ruff check .
    if ($LASTEXITCODE -ne 0) { throw "ruff check failed" }

    uv run ruff format --check .
    if ($LASTEXITCODE -ne 0) { throw "ruff format failed" }

    uv run mypy src
    if ($LASTEXITCODE -ne 0) { throw "mypy failed" }

    uv run pytest
    if ($LASTEXITCODE -ne 0) { throw "pytest failed" }
} finally {
    Pop-Location
}