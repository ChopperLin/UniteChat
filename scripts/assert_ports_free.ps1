param(
    [Parameter(Mandatory=$true)]
    [string]$PortsCsv,

    [switch]$ShowDetails
)

$ports = $PortsCsv.Split(',') | ForEach-Object { $_.Trim() } | Where-Object { $_ } | ForEach-Object {
    $p = 0
    if (-not [int]::TryParse($_, [ref]$p)) {
        throw "Invalid port: '$_'"
    }
    $p
}

$listeners = @()

if (Get-Command Get-NetTCPConnection -ErrorAction SilentlyContinue) {
    foreach ($p in $ports) {
        $listeners += Get-NetTCPConnection -State Listen -LocalPort $p -ErrorAction SilentlyContinue
    }
} else {
    $netstat = & netstat -ano
    foreach ($p in $ports) {
        $pattern = ":$p\s+.*LISTENING\s+(\d+)$"
        foreach ($line in $netstat) {
            $m = [regex]::Match($line, $pattern)
            if ($m.Success) {
                $pid = [int]$m.Groups[1].Value
                $listeners += [pscustomobject]@{ LocalPort = $p; OwningProcess = $pid }
            }
        }
    }
}

if ($listeners.Count -gt 0) {
    if ($ShowDetails) {
        $listeners |
            Select-Object LocalPort, OwningProcess |
            Sort-Object LocalPort, OwningProcess -Unique |
            ForEach-Object {
                $pid = $_.OwningProcess
                $name = $null
                try { $name = (Get-Process -Id $pid -ErrorAction SilentlyContinue).ProcessName } catch {}
                if ($name) {
                    Write-Output ("Port {0} LISTENING by PID {1} ({2})" -f $_.LocalPort, $pid, $name)
                } else {
                    Write-Output ("Port {0} LISTENING by PID {1}" -f $_.LocalPort, $pid)
                }
            }
    }
    exit 1
}

exit 0
