# Guía: retomar el proyecto IoT-SDN-AI

**Fecha base:** 2026-05-11
**Estado verificado hoy:** stack levantado, controller procesando tráfico real, anti-spoof aprendiendo bindings, REST API IoT responde.

---

## 0. Antes de empezar (PC anfitrión)

- Cerrar **HTGame** y apps pesadas (PC 16GB, VM usa 4GB + 4GB swap).
- Verificar que Hyper-V esté activo: PowerShell → `Get-WindowsOptionalFeature -Online -FeatureName Microsoft-Hyper-V` debe decir `State : Enabled`.

---

## 1. Arrancar la VM

```powershell
& "C:\Program Files\Multipass\bin\multipass.exe" start iotsdn
& "C:\Program Files\Multipass\bin\multipass.exe" list
```

Esperar `State: Running` con una IPv4 (suele ser `172.26.x.x`).

---

## 2. Re-montar el workspace (CRÍTICO — se cae con cada reboot)

```powershell
& "C:\Program Files\Multipass\bin\multipass.exe" umount iotsdn
& "C:\Program Files\Multipass\bin\multipass.exe" mount C:\Users\mquui\iot-sdn-ai iotsdn:/home/ubuntu/iot-sdn-ai
```

**Verifica:**

```powershell
& "C:\Program Files\Multipass\bin\multipass.exe" exec iotsdn -- ls /home/ubuntu/iot-sdn-ai
```

Debe listar `SdnShare`, `iot`, `docker-compose.override.yaml`, etc. Si sale vacío, el mount no quedó — repetir paso.

---

## 3. Re-activar swap (también se cae con reboot)

```powershell
& "C:\Program Files\Multipass\bin\multipass.exe" exec iotsdn -- sudo swapon /swapfile
& "C:\Program Files\Multipass\bin\multipass.exe" exec iotsdn -- swapon --show
```

Debe mostrar `/swapfile file 4G`.

---

## 4. Levantar el stack Docker

```powershell
& "C:\Program Files\Multipass\bin\multipass.exe" exec iotsdn -- bash -c "cd /home/ubuntu/iot-sdn-ai && docker compose -f SdnShare/docker-compose.yaml -f docker-compose.override.yaml up -d"
```

Espera ~30s. Luego:

```powershell
& "C:\Program Files\Multipass\bin\multipass.exe" exec iotsdn -- docker ps
```

Debe haber **2 containers up:**
- `sdnshare-controller-1` → `Up X seconds (healthy)`
- `sdnshare-mininet-1` → `Up X seconds`

---

## 5. Lanzar la topología (67 hosts / 10 switches)

```powershell
& "C:\Program Files\Multipass\bin\multipass.exe" exec iotsdn -- bash -c "cd /home/ubuntu/iot-sdn-ai && make -f Makefile.iot iot-topo"
```

Tarda 30-60s. **Deja ese comando corriendo** (mininet vive en foreground del docker exec).

Para verificar que cargó, en **otra terminal PowerShell:**

```powershell
& "C:\Program Files\Multipass\bin\multipass.exe" exec iotsdn -- bash -c "docker exec sdnshare-mininet-1 ovs-vsctl list-br"
```

Debe listar 10: `s_iot_0..s_iot_7`, `s_spine_1`, `s_spine_2`.

---

## 6. Smoke test (verifica que TODO funciona)

```powershell
& "C:\Program Files\Multipass\bin\multipass.exe" exec iotsdn -- bash -c "docker exec sdnshare-mininet-1 ovs-ofctl -O OpenFlow13 dump-flows s_spine_1 | wc -l"
```
**Esperado:** ≥10 (flows reales instalados por controller).

```powershell
& "C:\Program Files\Multipass\bin\multipass.exe" exec iotsdn -- curl -s http://localhost:8080/iot/status
```
**Esperado:** `{"active": []}` (sin mitigaciones activas, normal en idle).

```powershell
& "C:\Program Files\Multipass\bin\multipass.exe" exec iotsdn -- bash -c "curl -s http://localhost:8080/iot/antispoof/bindings | head -c 200"
```
**Esperado:** JSON con `bindings` reales (dpid, ip, mac, port, ts).

Si los tres responden bien → **todo funciona**.

---

## 7. Re-correr pipeline completo (opcional, ya hecho 2026-05-08)

Solo si quieres regenerar dataset/modelos. Toma ~40 min.

```bash
# entrar a la VM por shell:
& "C:\Program Files\Multipass\bin\multipass.exe" shell iotsdn

# dentro de la VM:
cd ~/iot-sdn-ai
RUN=run_$(date +%Y%m%d-%H%M%S)
make -f Makefile.iot iot-attack-all                          # 14 ataques
make -f Makefile.iot iot-capture RUN=$RUN IFACE=s_spine_1-eth1
make -f Makefile.iot iot-pipeline RUN=$RUN                   # PCAP → CSV
make -f Makefile.iot iot-train RUN=$RUN                      # 5 modelos
make -f Makefile.iot iot-report RUN=$RUN                     # PDF
```

**OJO:** Captura genera 3+ GB de pcap. Vive en `/home/ubuntu/iot_run/` (FS local VM), **NO** en el mount 9p (no soporta archivos >3GB).

---

## 8. Apagar al terminar

```powershell
& "C:\Program Files\Multipass\bin\multipass.exe" exec iotsdn -- bash -c "cd /home/ubuntu/iot-sdn-ai && docker compose -f SdnShare/docker-compose.yaml -f docker-compose.override.yaml down"
& "C:\Program Files\Multipass\bin\multipass.exe" stop iotsdn
```

---

## Resultados ya guardados (run_20260508-013842)

- Dataset balanceado: `~/iot_run/dataset_p1p2_clean13.csv` (en VM)
- Modelos: RF/XGB/MLP F1≈0.60, IsoForest/OCSVM attack_f1≈0.95
- PDF: `data/processed/run_20260508-013842/report_run_real_v2.pdf`

---

## Troubleshooting rápido

| Síntoma | Causa | Fix |
|---|---|---|
| `ls /home/ubuntu/iot-sdn-ai` vacío | Mount cayó tras reboot | Re-correr **paso 2** |
| `docker ps` vacío | Stack abajo | **Paso 4** |
| OVS muestra puertos `eth1, eth3...` con "could not open" | Topo no lanzada o zombie del run previo | **Paso 5** (o `docker compose down && up`) |
| `/iot/status` da 404 | Apps custom no cargaron | `docker logs sdnshare-controller-1` → buscar tracebacks |
| Mininet container exit en <30s | Estás en WSL2, no Hyper-V | Cambiar driver: `multipass set local.driver=hyperv` |
| RAM se acaba | HTGame u otro proceso abierto | Cerrar antes de `multipass start` |

---

## Plan defensa (deadline 2026-05-17, **6 días**)

1. **Hoy 11:** insertar números reales en `docs/defensa/DEFENSA-slides.md`
2. **12-13:** demo grabada (`docs/guias/GUIA-grabar-demo.md`) + cross-eval CIC si dataset listo
3. **14-16:** practicar cronometrado
4. **17:** defensa
