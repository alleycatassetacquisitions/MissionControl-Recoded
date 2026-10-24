# Run in Windows Terminal / PowerShell OUTSIDE Cursor (password prompts hang the IDE).
# Stages flat MCS + GBN trees on Proxmox and runs push-peer-hub-venue.sh.
#
#   cd <repo>
#   powershell -ExecutionPolicy Bypass -File ProxmoxInstallFiles\push-peer-hub-from-pc.ps1
#
# Optional smoke after push (venue URLs):
#   $env:SMOKE=1; $env:CENTRAL_PRIMARY='https://...'; $env:MCS_URL='http://...:8700'; ...
#
param(
  [string]$ProxmoxHost = "10.10.50.205",
  [string]$User = "root",
  [switch]$Smoke
)

$ErrorActionPreference = "Stop"
$Repo = Split-Path -Parent $PSScriptRoot
$Remote = "${User}@${ProxmoxHost}"

Write-Host "==> Staging flat MCS + GBN trees on $ProxmoxHost"
ssh $Remote "rm -rf /root/mcs-src /root/gbn-src; mkdir -p /root/mcs-src /root/gbn-src"

scp -r "$Repo\Apps\Master_Control_Server\Server_Component\*" "${Remote}:/root/mcs-src/"
scp -r "$Repo\Apps\Galactic_Bounty_Network\Server_Component\*" "${Remote}:/root/gbn-src/"
scp "$Repo\ProxmoxInstallFiles\lib\push-server-component.sh" "${Remote}:/root/"
scp "$Repo\ProxmoxInstallFiles\push-peer-hub-venue.sh" "${Remote}:/root/"

$remoteCmd = "bash /root/push-peer-hub-venue.sh"
if ($Smoke -or $env:SMOKE -eq "1") {
  $primary = $env:CENTRAL_PRIMARY
  $mcs = $env:MCS_URL
  $gbn = $env:GBN_URL
  $clock = $env:HOST_CLOCK_URL
  if (-not $primary -or -not $mcs -or -not $gbn) {
    throw "Smoke requires env CENTRAL_PRIMARY, MCS_URL, GBN_URL (optional HOST_CLOCK_URL)"
  }
  $remoteCmd = "SMOKE=1 CENTRAL_PRIMARY='$primary' MCS_URL='$mcs' GBN_URL='$gbn' HOST_CLOCK_URL='$clock' bash /root/push-peer-hub-venue.sh"
}

Write-Host "==> Push on host"
ssh $Remote $remoteCmd

Write-Host "==> Done. Inspect with Bearer GET {mcs}/config/status after a Registration sync_now or CC Save."
