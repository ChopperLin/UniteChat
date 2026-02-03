param(
    [string]$HostName = '127.0.0.1',

    [Parameter(Mandatory=$true)]
    [int]$Port,

    [int]$Retries = 20,
    [int]$DelayMilliseconds = 500
)

for ($i = 0; $i -lt $Retries; $i++) {
    try {
        $addresses = @()
        try {
            $addresses = [System.Net.Dns]::GetHostAddresses($HostName)
        } catch {
            $addresses = @()
        }

        if (-not $addresses -or $addresses.Count -eq 0) {
            $addresses = @($HostName)
        }

        foreach ($addr in $addresses) {
            try {
                $client = New-Object System.Net.Sockets.TcpClient
                $client.Connect($addr, $Port)
                $client.Close()
                exit 0
            } catch {
                # try next address
            }
        }
    } catch {
        # ignore
    }
    Start-Sleep -Milliseconds $DelayMilliseconds
}

exit 1
