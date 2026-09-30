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

## 4. Guion (90 segundos) — mitigación AUTOMÁTICA

Antes de grabar (en la VM): topología arriba (`make iot-topo`) y lazo en vivo
(`make iot-live-start`). En una terminal: `tail -f /tmp/live_detector.log | grep ACTION`.

```
[0:00] "Demo del proyecto IoT-SDN-AI: 67 hosts, 10 conmutadores OpenFlow."
       Mostrar el diagrama del lazo (docs/tesis/figuras/lazo_cerrado.png).

[0:10] "El detector analiza el tráfico cada 2 segundos. Nadie va a tocar nada."
       Mostrar el log del detector: ventanas [CHUNK] sin incidentes.

[0:20] "Lanzo un UDP flood desde el host atacante."
       > make iot-attack SCN=udp_flood

[0:25] "En unos 3 segundos el detector lo identifica y pide la regla."
       Señalar la línea: [ACTION] drop {'src_ip': '10.10.0.99'} UDP_FLOOD ... lat=…s

[0:40] "El controlador instaló la regla en los 10 conmutadores."
       > make iot-mit-status
       > docker exec sdnshare-mininet-1 ovs-ofctl -O OpenFlow13 dump-flows s_iot_0 table=0 | grep 10.10.0.99

[0:60] "El tráfico del atacante cae a cero; los sensores legítimos siguen funcionando."

[1:15] "En la evaluación: 39 de 39 ataques mitigados, mediana 2,5 s, cero falsas alarmas."
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
2. Terminal con `make iot-live-start` activo y el log del detector visible.
3. `/iot/status` con la entrada activa.
4. `ovs-ofctl dump-flows` con la flow-rule de drop.
5. Dashboard durante el ataque (KPIs en rojo).
6. Dashboard después del unban (vuelta a verde).

Pega los 6 screenshots en una slide adicional ("Demo — capturas") como respaldo absoluto.
