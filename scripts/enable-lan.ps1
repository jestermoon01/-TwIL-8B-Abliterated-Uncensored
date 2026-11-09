# Run once in an administrator PowerShell on the trusted local network.
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$profile = Get-NetConnectionProfile -InterfaceAlias 'Ethernet'
Set-NetConnectionProfile -InterfaceIndex $profile.InterfaceIndex -NetworkCategory Private
$ruleName = 'TwIL-llama-server-8080-LAN'
if (!(Get-NetFirewallRule -Name $ruleName -ErrorAction SilentlyContinue)) {
    New-NetFirewallRule -Name $ruleName -DisplayName 'TwIL llama-server 8080 LAN' `
        -Direction Inbound -Protocol TCP -LocalPort 8080 -Action Allow `
        -Profile Private -RemoteAddress LocalSubnet `
        -Program (Join-Path $projectRoot 'bin-b10000/llama-server.exe') | Out-Null
}
Get-NetConnectionProfile -InterfaceAlias 'Ethernet' | Select-Object Name, NetworkCategory
Get-NetFirewallRule -Name $ruleName | Select-Object Name, Enabled, Profile, Action
