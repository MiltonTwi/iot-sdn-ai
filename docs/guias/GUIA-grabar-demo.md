# Guía — Grabar demo de respaldo (10 min)

**Por qué:** si el día de defensa la red falla, abres el video. Insurance.

---

## 1. Software (gratis)

- **Windows:** OBS Studio (`winget install OBSProject.OBSStudio`).
- **Alternativa rápida:** Win+G abre Game Bar → "Capturar".
- **Para mobile/celular:** ScreenRec o screenshot del dashboard en su celular.

---

## 2. Setup escena OBS

1. Abrir OBS.
2. Añadir fuente → "Captura de pantalla" → tu monitor principal.
3. Añadir fuente → "Captura de audio (entrada)" → micrófono.
4. Resolución: 1920×1080, 30 fps.
5. Salida: MP4, bitrate 5000 kbps.
6. Carpeta destino: `C:\Users\mquui\iot-sdn-ai\docs\video\`.

---

## 3. Preparar pantalla

Abre 4 ventanas, organizadas:

| Cuadrante | Contenido |
|---|---|
| Izq-arriba | PowerShell con prompt limpio |
| Izq-abajo | Editor de código mostrando `iot/controller/iot_mitigation.py` |
| Der-arriba | Navegador en `http://localhost:8000` (dashboard) |
| Der-abajo | Navegador en `http://localhost:3000` (Grafana) |

---

## 4. Guion (90 segundos)

```
[0:00] "Demo del proyecto IoT-SDN-AI."
       Mostrar dashboard izquierdo: 67 dispositivos, 7 zonas activas.

[0:10] "Lanzo el ataque syn_flood desde el host atacante."
       En PowerShell:
       > make -f Makefile.iot iot-demo SCN=syn_flood

[0:25] "El detector ML procesa los flujos en tiempo real."
       Mostrar dashboard: PPS sube de ~400 a ~5000.

[0:40] "El bridge llama a /iot/mitigate con confianza > 0.85."
       En PowerShell separada:
       > curl http://localhost:8080/iot/status

       Apunta a la respuesta JSON: src_ip=10.10.0.99, action=drop, dpids=[...]

[0:55] "El controlador SDN instala flow-rules en 8 switches."
       En PowerShell:
       > docker exec sdnshare-mininet-1 ovs-ofctl -O OpenFlow13 dump-flows s_iot_0 | grep priority=200

       Lee la línea: priority=200, nw_src=10.10.0.99 actions=drop

[1:10] "El tráfico atacante se bloquea. El dashboard muestra mitigación activa."
       Apunta al dashboard: card de ataques activos = 1, con etiqueta SYN_FLOOD.

[1:25] "Tras 60 segundos la regla expira; o se libera con /iot/unban."

[1:35] "Cero impacto en sensores legítimos durante todo el ataque."

[1:30] FIN.
```

---

## 5. Test ANTES de grabar

```powershell
# 1) verifica stack arriba:
wsl -- docker ps

# 2) verifica controller responde:
curl http://localhost:8080/iot/status

# 3) verifica dashboard:
curl http://localhost:8000/api/zones
```

Si algún test falla, NO grabes. Arregla primero.

---

## 6. Toma 2-3 takes

Primer take siempre sale mal. Toma 2 = bueno. Toma 3 = excelente.

Edita en CapCut (gratis) o solo recorta inicio/final con OBS.

---

## 7. Plan B (si no puedes grabar)

Captura screenshots de:
1. Dashboard antes del ataque.
2. PowerShell con `make iot-demo` corriendo.
3. `/iot/status` con la entrada activa.
4. `ovs-ofctl dump-flows` con la flow-rule de drop.
5. Dashboard durante el ataque (KPIs en rojo).
6. Dashboard después del unban (vuelta a verde).

Pega los 6 screenshots en una slide adicional ("Demo — capturas") como respaldo absoluto.
