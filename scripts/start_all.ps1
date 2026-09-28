# ════════════════════════════════════════════════════════════════════
# start_all.ps1 — secuencia end-to-end
# ════════════════════════════════════════════════════════════════════
param(
  [string]$Run = ("run_" + (Get-Date -Format "yyyyMMdd-HHmmss")),
  [int]$AttackDuration = 60,
  [switch]$SkipAttacks,
  [switch]$SkipTrain
)

$ErrorActionPreference = "Stop"

Write-Host "═══ IoT-SDN-AI start_all  RUN=$Run ═══" -ForegroundColor Cyan

Write-Host "[1/7] env_check..." -ForegroundColor Yellow
& "$PSScriptRoot\env_check.ps1"

Write-Host "[2/7] Generar topología..." -ForegroundColor Yellow
python iot\topology\generate_topology.py

Write-Host "[3/7] Levantar stack docker..." -ForegroundColor Yellow
make -f Makefile.iot iot-up

Write-Host "[4/7] Iniciar topología en mininet (background)..." -ForegroundColor Yellow
Start-Process -NoNewWindow -FilePath "make" -ArgumentList "-f","Makefile.iot","iot-topo"
Start-Sleep -Seconds 15

if (-not $SkipAttacks) {
  Write-Host "[5/7] Lanzar 14 ataques..." -ForegroundColor Yellow
  make -f Makefile.iot iot-attack-all
} else { Write-Host "[5/7] Ataques omitidos (-SkipAttacks)" -ForegroundColor DarkYellow }

Write-Host "[6/7] Procesar pipeline RUN=$Run..." -ForegroundColor Yellow
make -f Makefile.iot iot-pipeline RUN=$Run

if (-not $SkipTrain) {
  Write-Host "[7/7] Entrenar 5 modelos..." -ForegroundColor Yellow
  make -f Makefile.iot iot-train RUN=$Run
  make -f Makefile.iot iot-compare
} else { Write-Host "[7/7] Train omitido (-SkipTrain)" -ForegroundColor DarkYellow }

Write-Host ""
Write-Host "DASHBOARDS:" -ForegroundColor Green
Write-Host "  http://localhost:8000   IoT-SDN-AI"
Write-Host "  http://localhost:3000   Grafana (admin/admin)"
Write-Host "  http://localhost:8080   FlowManager"
Write-Host ""
Write-Host "Acceso celular: .\scripts\tunnel_phone.ps1 lan" -ForegroundColor Yellow
