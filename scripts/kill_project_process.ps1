param(
    [Parameter(Mandatory = $false)]
    [string]$Root = "",

    [Parameter(Mandatory = $false)]
    [int]$TargetPid = 0,

    [Parameter(Mandatory = $false)]
    [string]$TargetPidFile = "",

    [Parameter(Mandatory = $false)]
    [string[]]$TargetPidFiles = @(),

    [Parameter(Mandatory = $false)]
    [int[]]$Ports = @()

    ,
    [Parameter(Mandatory = $false)]
    [string]$PortsCsv = ""
)

$ErrorActionPreference = 'SilentlyContinue'

function Normalize-Root([string]$p) {
    if (-not $p) { return "" }
    try {
        $full = [System.IO.Path]::GetFullPath($p)
        return $full.TrimEnd([System.IO.Path]::DirectorySeparatorChar, [System.IO.Path]::AltDirectorySeparatorChar)
    } catch {
        return ($p.TrimEnd('\\','/'))
    }
}

$Root = Normalize-Root $Root

if ((-not $Ports -or $Ports.Count -eq 0) -and $PortsCsv) {
    $tmp = @()
    foreach ($part in ($PortsCsv -split '[,;\s]+' | Where-Object { $_ -and $_.Trim() })) {
        $v = 0
        if ([int]::TryParse($part.Trim(), [ref]$v) -and $v -gt 0) {
            $tmp += $v
        }
    }
    $Ports = $tmp
}

function Get-PidFromFile([string]$path) {
    try {
        if (-not (Test-Path -LiteralPath $path)) { return 0 }
        $content = Get-Content -LiteralPath $path -ErrorAction SilentlyContinue
        if (-not $content -or $content.Count -lt 1) { return 0 }
        return [int]$content[0]
    } catch {
        return 0
    }
}

function Get-PidsFromFiles([string[]]$paths) {
    $set = New-Object 'System.Collections.Generic.HashSet[int]'
    foreach ($p in ($paths | Where-Object { $_ })) {
        $pid = Get-PidFromFile $p
        if ($pid -gt 0) { [void]$set.Add([int]$pid) }
    }
    return $set
}

function Kill-Tree([int]$processId) {
    if ($processId -le 0) { return }

    # Prefer taskkill on Windows for reliable tree termination.
    try {
        & taskkill /PID $processId /T /F | Out-Null
        return
    } catch {
        # fall back
    }

    try {
        $kids = Get-CimInstance Win32_Process -Filter ("ParentProcessId=" + $processId)
        foreach ($k in $kids) {
            Kill-Tree -processId ([int]$k.ProcessId)
        }
    } catch {
        # ignore
    }

    try {
        Stop-Process -Id $processId -Force
    } catch {
        # ignore
    }
}

function Get-ListeningPidsByPorts([int[]]$ports) {
    $pidSet = New-Object 'System.Collections.Generic.HashSet[int]'
    if (-not $ports -or $ports.Count -eq 0) { return $pidSet }

    $getNetTcp = Get-Command -Name Get-NetTCPConnection -ErrorAction SilentlyContinue
    if ($getNetTcp) {
        try {
            $conns = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue
            foreach ($c in $conns) {
                foreach ($p in $ports) {
                    if ($c.LocalPort -eq $p) {
                        [void]$pidSet.Add([int]$c.OwningProcess)
                        break
                    }
                }
            }
        } catch {
            # ignore
        }
        # 某些 Windows 环境下 Get-NetTCPConnection 可能拿不到监听信息；此时回退到 netstat
        if ($pidSet.Count -gt 0) { return $pidSet }
    }

    $lines = & netstat -ano 2>$null
    foreach ($line in $lines) {
        foreach ($p in $ports) {
            if ($line -match (':[ ]?' + $p + '\s') -and $line -match '\sLISTENING\s+(\d+)\s*$') {
                [void]$pidSet.Add([int]$Matches[1])
                break
            }
        }
    }

    return $pidSet
}

function Should-KillByRoot([int]$processId) {
    if (-not $Root) { return $true }
    if ($processId -le 0) { return $false }

    try {
        $p = Get-CimInstance Win32_Process -Filter ("ProcessId=" + $processId)
        if (-not $p) { return $false }
        $cmd = ($p.CommandLine | Out-String)
        $exe = ($p.ExecutablePath | Out-String)
        $needle = $Root.ToLowerInvariant()
        if ($cmd -and $cmd.ToLowerInvariant().Contains($needle)) { return $true }
        if ($exe -and $exe.ToLowerInvariant().Contains($needle)) { return $true }
    } catch {
        return $false
    }

    return $false
}


# 1) Kill explicit PID / PID file
if ($TargetPid -le 0 -and $TargetPidFile) {
    $TargetPid = Get-PidFromFile $TargetPidFile
}
if ($TargetPid -gt 0) {
    Kill-Tree -processId $TargetPid
}
if ($TargetPidFile) {
    try { Remove-Item -LiteralPath $TargetPidFile -Force } catch {}
}

if ($TargetPidFiles -and $TargetPidFiles.Count -gt 0) {
    $pidsFromFiles = Get-PidsFromFiles -paths $TargetPidFiles
    foreach ($pid in $pidsFromFiles) {
        Kill-Tree -processId $pid
    }
    foreach ($f in $TargetPidFiles) {
        if ($f) {
            try { Remove-Item -LiteralPath $f -Force } catch {}
        }
    }
}

# 2) Kill listeners by ports
if ($Ports -and $Ports.Count -gt 0) {
    $pids = Get-ListeningPidsByPorts -ports $Ports
    foreach ($processId in $pids) {
        if (Should-KillByRoot -processId $processId) {
            Kill-Tree -processId $processId
        }
    }
}
