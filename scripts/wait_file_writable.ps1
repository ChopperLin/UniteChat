param(
    [Parameter(Mandatory = $true)]
    [string]$Path,

    [int]$Retries = 30,
    [int]$DelayMilliseconds = 200,

    [switch]$CreateIfMissing
)

$ErrorActionPreference = 'SilentlyContinue'

if ($CreateIfMissing) {
    try {
        $dir = Split-Path -Parent $Path
        if ($dir -and -not (Test-Path -LiteralPath $dir)) {
            New-Item -ItemType Directory -Force -Path $dir | Out-Null
        }
        if (-not (Test-Path -LiteralPath $Path)) {
            New-Item -ItemType File -Force -Path $Path | Out-Null
        }
    } catch {
        # ignore
    }
}

for ($i = 0; $i -lt $Retries; $i++) {
    try {
        $fs = [System.IO.File]::Open($Path, [System.IO.FileMode]::OpenOrCreate, [System.IO.FileAccess]::ReadWrite, [System.IO.FileShare]::ReadWrite)
        $fs.Close()
        exit 0
    } catch {
        Start-Sleep -Milliseconds $DelayMilliseconds
    }
}

exit 1
