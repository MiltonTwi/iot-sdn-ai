# PASO 03 — Generador de topología Mininet IoT

**Fecha:** 2026-05-04
**Archivos:**
- `iot/topology/generate_topology.py` — convierte `zones.yaml` → `network_config.iot.yaml`
- `iot/topology/mn_iot_topo.py` — construye la red Mininet desde el YAML generado

---

## Por qué dos archivos

`generate_topology.py` es **declarativo** (corre en host, sin Mininet). Convierte el catálogo humano (`zones.yaml`) al formato que entiende el script Mininet del repo base (`switches`, `links`, `hosts`).

`mn_iot_topo.py` es **imperativo** (corre dentro del container `mininet`, requiere root). Lee el YAML generado y construye la red.

Separación → puedes regenerar topologías sin tocar Mininet, hacer diff sobre YAML, y versionar la fuente de verdad (`zones.yaml`) sin contaminar con detalles de mac/port.

---

## Topología resultante

```
                 ┌─────────────┐         ┌─────────────┐
                 │  s_spine_1  │         │  s_spine_2  │
                 └──┬───┬───┬──┘         └──┬───┬───┬──┘
                    │   │   │ (full mesh)   │   │   │
       ┌────────────┼───┼───┼───┬───────────┼───┼───┼────────────┐
       ▼            ▼   ▼   ▼   ▼           ▼   ▼   ▼            ▼
   ┌────────┐  ┌────────┐  ...                          ┌────────┐
   │s_iot_0 │  │s_iot_1 │  ...                          │s_iot_7 │
   │ infra  │  │ home   │                               │ retail │
   └───┬────┘  └───┬────┘                               └───┬────┘
       │           │                                         │
   7 servers   15 hosts                                  5 hosts
```

- **2 spines + 8 leaves + 70 hosts** (63 IoT + 7 servers).
- 16 enlaces inter-switch (full mesh 2x8).
- IDs OpenFlow: spines 1,2; leaves 10..17.

---

## Cómo correr

### Generar el YAML (host Windows o WSL):

```powershell
cd C:\Users\mquui\iot-sdn-ai
python iot\topology\generate_topology.py
```

Salida esperada:
```
Generado: iot/topology/network_config.iot.yaml
  switches=10  links=16  hosts=70
```

### Levantar la topología en Mininet (dentro del container):

```bash
# desde host (Windows PowerShell o WSL)
docker compose exec mininet python3 /root/iot/topology/mn_iot_topo.py \
    /root/iot/topology/network_config.iot.yaml \
    --auto-traffic
```

`--auto-traffic` arranca automáticamente los simuladores de dispositivos en cada host (PASO-04). Sin esa bandera la topología queda solo con la red, útil para tests manuales.

---

## Verificación

Dentro de Mininet CLI:
```
mininet> nodes               # debe listar 70 hosts + 10 switches
mininet> pingall             # 0% loss esperado (puede tardar 30-60s con 70 hosts)
mininet> cam_front ifconfig  # ver IP 10.10.1.10 asignada
```

Si `pingall` falla → el controller Ryu no está propagando flujos. Revisar `make restart` y FlowManager en `http://localhost:8080`.

---

## Volumen mount necesario

El container `mininet` del base solo monta `infra/topology|configs|attacks` y `scripts`. Para que vea `iot/`:

`docker-compose.override.yaml` añadirá:

```yaml
services:
  mininet:
    volumes:
      - ./iot:/root/iot
```

(Se aplica en PASO-10.)

---

## Próximo paso

`PASO-04-simuladores.md` — los procesos que generan tráfico en cada host.
