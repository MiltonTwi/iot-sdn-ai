# ════════════════════════════════════════════════════════════════════
# tunnel_phone.ps1 — expone el dashboard al celular
# ════════════════════════════════════════════════════════════════════
# Uso:
#   .\scripts\tunnel_phone.ps1 lan          (IP LAN + firewall rule)
#   .\scripts\tunnel_phone.ps1 cloudflared  (URL pública trycloudflare.com)
#   .\scripts\tunnel_phone.ps1 ngrok        (URL pública ngrok)
# ════════════════════════════════════════════════════════════════════

param(
  [Parameter(Mandatory=$true)]
  [ValidateSet("lan","cloudflared","ngrok")]
  [string]$mode,
  [int]$port = 8000
)

switch ($mode) {
  "lan" {
    $ip = (Get-NetIPAddress -AddressFamily IPv4 |
           Where-Object { $_.InterfaceAlias -notmatch "Loopback|vEthernet|WSL" -and $_.IPAddress -notlike "169.*" } |
           Select-Object -First 1).IPAddress
    if (-not $ip) { Write-Host "No detecté IP LAN" -ForegroundColor Red; exit 1 }
    Write-Host "Abriendo puerto $port en firewall..." -ForegroundColor Cyan
    New-NetFirewallRule -DisplayName "IoT Dashboard $port" -Direction Inbound -LocalPort $port -Protocol TCP -Action Allow -ErrorAction SilentlyContinue | Out-Null
    Write-Host ""
    Write-Host "  Desde el celular (mismo Wi-Fi):" -ForegroundColor Green
    Write-Host "    http://${ip}:${port}" -ForegroundColor Yellow
    Write-Host ""
  }
  "cloudflared" {
    if (-not (Get-Command cloudflared -ErrorAction SilentlyContinue)) {
      Write-Host "cloudflared no instalado. winget install --id Cloudflare.cloudflared" -ForegroundColor Red
      exit 1
    }
    Write-Host "Iniciando tunel cloudflared --> http://localhost:${port}" -ForegroundColor Cyan
    cloudflared tunnel --url "http://localhost:${port}"
  }
  "ngrok" {
    if (-not (Get-Command ngrok -ErrorAction SilentlyContinue)) {
      Write-Host "ngrok no instalado. winget install --id Ngrok.Ngrok" -ForegroundColor Red
      exit 1
    }
    Write-Host "Iniciando ngrok http ${port}" -ForegroundColor Cyan
    ngrok http $port
  }
}
