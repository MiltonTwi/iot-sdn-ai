# ════════════════════════════════════════════════════════════════════
# demo.ps1 — defensa-friendly: 90s end-to-end (ataque → detección → mitigación → recuperación)
# ════════════════════════════════════════════════════════════════════
param(
  [string]$Scenario = "syn_flood",
  [int]$Duration = 30,
  [string]$AttackerIp = "10.10.0.99",
  [string]$Controller = "http://localhost:8080",
  [string]$Dashboard = "http://localhost:8000"
)

$ErrorActionPreference = "Continue"

function Step([string]$msg, [string]$color = "Cyan") {
  Write-Host ""
  Write-Host (">>> {0}" -f $msg) -ForegroundColor $color
}

function Wait-Secs([int]$s) {
  for ($i = $s; $i -gt 0; $i--) {
    Write-Host -NoNewline ("`r  esperando {0}s   " -f $i)
    Start-Sleep -Seconds 1
  }
  Write-Host "`r                       "
}

function Get-Mitigation {
  try {
    Invoke-RestMethod -Uri "$Controller/iot/status" -TimeoutSec 3 -ErrorAction Stop
  } catch { @{ active = @() } }
}

Write-Host "═══════════════════════════════════════════════════════════════════" -ForegroundColor Magenta
Write-Host "  IoT-SDN-AI  —  DEMO  ($Scenario, ${Duration}s)" -ForegroundColor Magenta
Write-Host "  Dashboard: $Dashboard" -ForegroundColor Yellow
Write-Host "═══════════════════════════════════════════════════════════════════" -ForegroundColor Magenta

Step "1/6  Verificando stack"
$st = Get-Mitigation
Write-Host "  controller OK ($($st.active.Count) mitigaciones activas)"

Step "2/6  Estado inicial (sin ataque)"
Wait-Secs 5

Step "3/6  Lanzando ataque $Scenario desde $AttackerIp" "Red"
$compose = "docker compose -f SdnShare/docker-compose.yaml -f docker-compose.override.yaml"
Start-Process -NoNewWindow -FilePath "cmd" -ArgumentList "/c","$compose exec -T mininet python3 /root/iot/attacks/runner.py --scenario $Scenario --duration $Duration"
Start-Sleep -Seconds 3
Write-Host "  ataque corriendo... (revisa el dashboard, deberías ver pps subir)"

Step "4/6  Llamando al detector (simula confianza alta + acción drop)"
$body = @{ src_ip = $AttackerIp; action = "drop"; duration_s = ($Duration + 30) } | ConvertTo-Json -Compress
try {
  $r = Invoke-RestMethod -Uri "$Controller/iot/mitigate" -Method Post -ContentType "application/json" -Body $body -TimeoutSec 5
  Write-Host ("  → DROP instalado en dpids: {0}" -f ($r.dpids -join ", ")) -ForegroundColor Green
} catch {
  Write-Host "  [!] mitigación falló: $_" -ForegroundColor Red
  exit 1
}

Step "5/6  Verificando que la mitigación está activa"
Start-Sleep -Seconds 2
$st = Get-Mitigation
if ($st.active | Where-Object { $_.src_ip -eq $AttackerIp }) {
  $entry = $st.active | Where-Object { $_.src_ip -eq $AttackerIp }
  Write-Host "  ✓ activa: $($entry.action) — restan $([int]$entry.remaining_s)s en $($entry.dpids.Count) switches" -ForegroundColor Green
} else {
  Write-Host "  [!] no se ve la entrada en /iot/status" -ForegroundColor Yellow
}
Wait-Secs $Duration

Step "6/6  Limpieza — quitando mitigación"
Invoke-RestMethod -Uri "$Controller/iot/unban" -Method Post -ContentType "application/json" `
  -Body (@{ src_ip = $AttackerIp } | ConvertTo-Json -Compress) -TimeoutSec 3 | Out-Null
Write-Host "  ✓ unban OK"

Write-Host ""
Write-Host "═══════════════════════════════════════════════════════════════════" -ForegroundColor Magenta
Write-Host "  DEMO COMPLETA" -ForegroundColor Green
Write-Host "  Audit log: data/audit/mitigation.jsonl" -ForegroundColor Yellow
Write-Host "═══════════════════════════════════════════════════════════════════" -ForegroundColor Magenta
