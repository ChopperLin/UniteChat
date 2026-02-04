param(
    [Parameter(Mandatory = $true)]
    [string]$PortsCsv,

    [int]$Retries = 20,
    [int]$DelayMilliseconds = 250,

    [switch]$ShowDetails
)

$ErrorActionPreference = 'SilentlyContinue'

for ($i = 0; $i -lt $Retries; $i++) {
    & "$PSScriptRoot\assert_ports_free.ps1" -PortsCsv $PortsCsv -ShowDetails:$false
    if ($LASTEXITCODE -eq 0) {
        exit 0
    }
    Start-Sleep -Milliseconds $DelayMilliseconds
}

if ($ShowDetails) {
    & "$PSScriptRoot\assert_ports_free.ps1" -PortsCsv $PortsCsv -ShowDetails
}

exit 1
