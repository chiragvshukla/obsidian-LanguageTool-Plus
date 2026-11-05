# Full local check: lint, format, types, tests. Run from anywhere.
$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$gateway = Join-Path $PSScriptRoot "..\gateway"
Push-Location $gateway
try {
    uv sync
    uv run ruff check .
    uv run ruff format --check .
    uv run mypy src
    uv run pytest
} finally {
    Pop-Location
}