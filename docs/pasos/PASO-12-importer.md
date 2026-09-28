# PASO 12 — Importador automático de topologías

**Fecha:** 2026-05-04
**Archivo:** `iot/topology/importer.py`
**Ejemplos:** `iot/topology/examples/{ring4.json, fattree_k4.graphml}`

---

## Qué hace

Toma una topología en cualquier formato común y produce `network_config.iot.yaml` rellenando con las zonas/dispositivos declarados en `iot/zones.yaml`.

Stdlib pura — sin NetworkX, sin requests. Solo `xml.etree`, `json`, `urllib`, `ast`.

---

## Formatos soportados

| `--from` | Para qué | Detección de edges |
|---|---|---|
| `graphml` | Internet Topology Zoo, exports de yEd/NetworkX/Gephi | `attr type=edge|leaf|access|tor`; sino degree mínimo |
| `nx-json` | NetworkX `node_link_data()` exportado a JSON | degree mínimo |
| `mininet-py` | Cualquier script Mininet (parseo AST de `addSwitch/addHost/addLink`) | degree mínimo |
| `ryu-api` | Descubrimiento en vivo: `http://controller:8080/v1.0/topology` | degree mínimo |
| `json` | Formato propio simple `{switches:[…], links:[…]}` | degree mínimo |

---

## Reglas de poblado

1. **Detección de edges:** primero busca atributo `type` ∈ {`edge`, `leaf`, `access`, `tor`}. Si no, calcula degree de cada switch y elige los de degree mínimo (ring → todos son edges; fat-tree → solo ToR).
2. **Zona infra (servidores)** aterriza en el primer edge.
3. **Zonas IoT** se reparten **round-robin** sobre los edges restantes. Si hay más zonas que edges, varias zonas comparten edge.
4. **Re-IP automático:** todos los hosts se re-numeran como `<ip_prefix>.<zone_id>.<10+idx>`. El default `10.10` es configurable con `--ip-prefix`.
5. **MAC re-asignada** con OUI `02:1f:7d` (configurable).
6. **Puertos** de switch asignados secuencialmente en el orden de aparición de los enlaces.

---

## Ejemplos

### Ring de 4 switches (JSON propio)
```bash
make iot-import FROM=json INPUT=iot/topology/examples/ring4.json
```
Resultado: 4 edges (degree 2, todos iguales), las 7 zonas se distribuyen 2-2-2-1.

### Fat-tree k=4 (GraphML con atributos)
```bash
make iot-import FROM=graphml INPUT=iot/topology/examples/fattree_k4.graphml
```
Resultado: 4 core + 8 aggregation + 8 edge. Solo los `edge*` reciben zonas IoT (1 zona infra + 7 zonas, una por ToR).

### Script Mininet existente
```bash
make iot-import FROM=mininet-py INPUT=SdnShare/infra/topology/mn_threeswitch_topo.py
```

### Topology Zoo (Cogent.graphml por ejemplo)
```bash
make iot-import FROM=graphml INPUT=Cogent.graphml --ip-prefix 10.42
```

### Red SDN en vivo (Ryu corriendo)
```bash
make iot-import FROM=ryu-api INPUT=http://localhost:8080
```
Útil para overlay sobre una red real: descubre dpids+links via OpenFlow, luego cuelga IoT en los edges.

---

## Diff vs `generate_topology.py` original

| | `generate_topology.py` | `importer.py` |
|---|---|---|
| Estructura | spine-leaf hardcoded (2 spines + 1 leaf por zona) | cualquiera |
| Switches | autogenerados | tomados de la fuente externa |
| Distribución de zonas | 1 zona = 1 leaf nuevo | round-robin sobre edges existentes |
| Plan IP | fijo `10.10/16` | parametrizable `--ip-prefix` |
| Cambia formato salida | no | no — produce el mismo `network_config.iot.yaml` |

Conclusión: `mn_iot_topo.py` no necesita cambios — consume el mismo YAML de salida.

---

## Limitaciones

- **Mininet AST parser** asume patrones `obj.addSwitch('s1')` y similares. Variables computadas (`for i in range(N): self.addSwitch(f's{i}')`) no se expanden — habría que ejecutar el script. Pendiente para v2.
- **Edges detectados por degree** pueden equivocarse en topologías densas sin atributos. Workaround: añadir `<data key="type">edge</data>` en GraphML o `"type": "edge"` en JSON.
- **Ryu API** requiere que el controlador exponga `--observe-links` (ya activo en SdnShare).

---

## Tradeoffs

- **Re-IP completo** (no preserva las IP originales del archivo importado). Necesario porque los simuladores y los ataques referencian IPs según `zones.yaml`. Si se quisiera preservar, habría que reescribir también `runner.py` y el labeler — fuera de scope.
- **Sin pesos en distribución de zonas** — `round-robin` puro. Para topologías con edges de capacidad heterogénea, añadir `--strategy weighted` que lea capacidad desde attrs sería trivial (~20 líneas).
