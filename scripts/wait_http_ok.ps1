param(
    [Parameter(Mandatory=$true)]
    [string]$Url,

    [int]$Retries = 20,
    [int]$DelaySeconds = 1,
    [int]$TimeoutSec = 1
)

for ($i = 0; $i -lt $Retries; $i++) {
    try {
        $r = Invoke-WebRequest -UseBasicParsing -TimeoutSec $TimeoutSec -Uri $Url
        if ($r.StatusCode -eq 200) {
            exit 0
        }
    } catch {
        # ignore
    }
    Start-Sleep -Seconds $DelaySeconds
}

exit 1
