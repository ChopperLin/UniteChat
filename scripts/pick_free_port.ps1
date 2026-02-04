param(
    [Parameter(Mandatory = $true)]
    [string]$PreferredPortsCsv,

    [string]$BindHost = '127.0.0.1',

    [int]$FallbackStart = 20000,
    [int]$FallbackEnd = 65000,
    [int]$MaxFallbackTries = 200,

    [switch]$AllowEphemeral,

    [switch]$ShowDetails
)

$ErrorActionPreference = 'SilentlyContinue'

function Parse-Ports([string]$csv) {
    $ports = @()
    foreach ($part in ($csv -split '[,;\s]+' | Where-Object { $_ -and $_.Trim() })) {
        $v = 0
        if ([int]::TryParse($part.Trim(), [ref]$v) -and $v -gt 0 -and $v -le 65535) {
            $ports += $v
        }
    }
    return ($ports | Select-Object -Unique)
}

function Format-ExceptionReason([object]$ex) {
    if (-not $ex) { return '' }

    $msg = $ex.Message
    if (-not $msg) {
        try { $msg = $ex.ToString() } catch { $msg = '' }
    }

    try {
        if ($ex -is [System.Net.Sockets.SocketException]) {
            $msg = ("{0} (NativeErrorCode={1})" -f $msg, $ex.NativeErrorCode)
        } elseif ($ex -and $ex.HResult) {
            $msg = ("{0} (HResult=0x{1})" -f $msg, ($ex.HResult.ToString('X8')))
        }
    } catch {
        # ignore
    }
    return $msg
}

function Test-CanBind([string]$host, [int]$port) {
    try {
        $ip = [System.Net.IPAddress]::Parse($host)
    } catch {
        # If host isn't a literal IP, default to loopback.
        $ip = [System.Net.IPAddress]::Loopback
    }

    try {
        $listener = [System.Net.Sockets.TcpListener]::new($ip, $port)
        $listener.Start()
        $listener.Stop()
        return [pscustomobject]@{ Ok = $true; Reason = '' }
    } catch {
        return [pscustomobject]@{ Ok = $false; Reason = (Format-ExceptionReason $_.Exception) }
    }
}

$preferred = Parse-Ports $PreferredPortsCsv
$candidates = New-Object 'System.Collections.Generic.List[int]'
foreach ($p in $preferred) { $candidates.Add([int]$p) }

# Add a small list of historically stable local-dev ports (mid-range avoids many excluded high-port ranges).
foreach ($p in (12000..12010 + 14540..14560 + 15000..15010)) {
    if (-not $candidates.Contains($p)) { $candidates.Add([int]$p) }
}

# Fallback: probe a range for something bindable.
# Use a deterministic-ish sequence to be stable across runs.
$seed = [Math]::Abs(($PID + (Get-Date).Millisecond))
$rng = [System.Random]::new($seed)

# If caller didn't override, prefer a lower range which is less likely to be excluded.
if ($FallbackStart -eq 20000 -and $FallbackEnd -eq 65000) {
    $FallbackStart = 10240
    $FallbackEnd = 20000
}

for ($i = 0; $i -lt $MaxFallbackTries; $i++) {
    $p = $rng.Next($FallbackStart, $FallbackEnd)
    if (-not $candidates.Contains($p)) { $candidates.Add($p) }
}

foreach ($p in $candidates) {
    $r = Test-CanBind -host $BindHost -port $p
    if ($r.Ok) {
        Write-Output $p
        exit 0
    }

    if ($ShowDetails) {
        Write-Output ("Port {0} not bindable: {1}" -f $p, $r.Reason)
    }
}

# Last resort: ask OS for an ephemeral port (race-prone but usually fine for local dev)
if ($AllowEphemeral) {
    try {
        $ip = [System.Net.IPAddress]::Parse($BindHost)
    } catch {
        $ip = [System.Net.IPAddress]::Loopback
    }

    try {
        $listener = [System.Net.Sockets.TcpListener]::new($ip, 0)
        $listener.Start()
        $ephemeral = $listener.LocalEndpoint.Port
        $listener.Stop()
        if ($ephemeral -gt 0) {
            Write-Output $ephemeral
            exit 0
        }
    } catch {
        if ($ShowDetails) {
            Write-Output ("Ephemeral port allocation failed: {0}" -f (Format-ExceptionReason $_.Exception))
        }
    }
}

if ($ShowDetails) {
    Write-Output "No bindable port found. Try changing port range or run as admin if policy blocks binds."
}

exit 1
