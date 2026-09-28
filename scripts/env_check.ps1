# ════════════════════════════════════════════════════════════════════
# env_check.ps1 — valida prerequisitos
# ════════════════════════════════════════════════════════════════════
$ErrorActionPreference = "Stop"
$ok = $true

function Check($name, $cmd) {
  try {
    $v = & $cmd 2>&1 | Select-Object -First 1
    Write-Host "  [OK] $name : $v" -ForegroundColor Green
  } catch {
    Write-Host "  [!!] $name : NO INSTALADO" -ForegroundColor Red
    $script:ok = $false
  }
}

Write-Host ""
Write-Host "═══ env_check ═══" -ForegroundColor Cyan
Check "docker"        { docker --version }
Check "docker compose" { docker compose version }
Check "python"        { python --version }
Check "wsl"           { wsl --status }

Write-Host ""
if (Test-Path ".\SdnShare") { Write-Host "  [OK] SdnShare/ presente" -ForegroundColor Green }
else { Write-Host "  [!!] SdnShare/ no encontrado" -ForegroundColor Red; $ok=$false }
if (Test-Path ".\iot\zones.yaml") { Write-Host "  [OK] iot/zones.yaml presente" -ForegroundColor Green }
else { Write-Host "  [!!] iot/zones.yaml no encontrado" -ForegroundColor Red; $ok=$false }

Write-Host ""
Write-Host "Puertos a usar: 3000(grafana) 8000(dash) 8080(flow) 8086(influx) 9000(graphite) 9090(prom)" -ForegroundColor Cyan
$used = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | ForEach-Object { $_.LocalPort } | Sort-Object -Unique
foreach ($p in 3000,8000,8080,8086,9000,9090) {
  if ($used -contains $p) { Write-Host "  [!!] $p YA EN USO" -ForegroundColor Yellow }
  else { Write-Host "  [OK] $p libre" -ForegroundColor Green }
}

Write-Host ""
if ($ok) { Write-Host "TODO LISTO" -ForegroundColor Green }
else     { Write-Host "FALTAN PREREQUISITOS" -ForegroundColor Red; exit 1 }
