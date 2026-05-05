$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) {
    $py = Get-Command py -ErrorAction SilentlyContinue
}

if (-not $py) {
    Write-Error "No Python interpreter found. Install Python, then run: python -m experiments.user_analize.runner"
    exit 1
}

if ($py.Name -eq "py") {
    & py -m experiments.user_analize.runner
} else {
    & python -m experiments.user_analize.runner
}
