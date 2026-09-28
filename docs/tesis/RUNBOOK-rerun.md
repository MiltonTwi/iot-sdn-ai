# Runbook — re-correr el pipeline y actualizar la tesis

Estado guardado: 2026-09-08. Contexto: se aplicaron los fixes #1 (jitter en `iot/devices/runner.py`) y #2 (durations 180 s en `iot/attacks/catalog.yaml`). Falta re-correr para reflejarlos. Al re-correr, **los números de la tesis cambiarán** (F1 bajará de ~1,0 a valores realistas).

## 0. Desbloquear Hyper-V (una vez) — REQUIERE REINICIO
Ya se lanzó `docs\tesis\_fix_hyperv.ps1` con UAC. Si no se aplicó, en PowerShell **Administrador**:
```powershell
Enable-WindowsOptionalFeature -Online -FeatureName Microsoft-Hyper-V-All -All -NoRestart
bcdedit /set hypervisorlaunchtype auto
```
Luego **reiniciar**. Verificar: `& "C:\Program Files\Multipass\bin\multipass.exe" start iotsdn` no debe dar "Hyper-V Hypervisor is disabled".

## 1. Arrancar VM y preparar (se cae con cada reboot)
```powershell
$mp="C:\Program Files\Multipass\bin\multipass.exe"
& $mp start iotsdn
& $mp umount iotsdn
& $mp mount C:\Users\mquui\iot-sdn-ai iotsdn:/home/ubuntu/iot-sdn-ai
& $mp exec iotsdn -- ls /home/ubuntu/iot-sdn-ai        # debe listar SdnShare, iot, ...
& $mp exec iotsdn -- sudo swapon /swapfile
& $mp exec iotsdn -- bash -c "cd /home/ubuntu/iot-sdn-ai && docker compose -f SdnShare/docker-compose.yaml -f docker-compose.override.yaml up -d"
& $mp exec iotsdn -- docker ps                          # 2 containers up (controller healthy + mininet)
```

## 2. Topología (dejar corriendo en foreground)
```powershell
& $mp exec iotsdn -- bash -c "cd /home/ubuntu/iot-sdn-ai && make -f Makefile.iot iot-topo"
# en otra terminal, verificar 10 bridges:
& $mp exec iotsdn -- bash -c "docker exec sdnshare-mininet-1 ovs-vsctl list-br"
```

## 3. Re-correr pipeline (dentro de la VM, ~40 min)
```bash
& "C:\Program Files\Multipass\bin\multipass.exe" shell iotsdn
# dentro:
cd ~/iot-sdn-ai
RUN=run_$(date +%Y%m%d-%H%M%S)
make -f Makefile.iot iot-attack-all
make -f Makefile.iot iot-capture RUN=$RUN IFACE=s_spine_1-eth1
make -f Makefile.iot iot-pipeline RUN=$RUN
make -f Makefile.iot iot-train RUN=$RUN
make -f Makefile.iot iot-report RUN=$RUN
```
OJO: pcap vive en `~/iot_run/` (FS local VM), no en el mount 9p.

## 4. Actualizar la tesis
- Nuevas métricas en `data/processed/$RUN/` (metrics_final.json, cross_eval*.json, bootstrap_ci.json) y figuras png.
- Actualizar en `docs/tesis/actualizar-tesis.ps1`: `$TABLES` (modelos, por clase, cross, latencia, adversarial) y el texto de Resultados/Resumen/Conclusiones con los valores nuevos; apuntar `$IMG` al nuevo run si aplica.
- Cerrar Word y correr `& ".\docs\tesis\actualizar-tesis.ps1"`.

## Pendientes de fondo (opcional, mayor rigor)
- #3 rotar host atacante entre corridas (evitar leakage) + revisar SHAP de features host_*.
- #4 arreglar ARP_SPOOF y MIRAI_COORDINATED (bridge promiscuo).
- #5 medir throughput de la víctima antes/después de la mitigación (extender `scripts/debug/verify_mitigation.py`).
