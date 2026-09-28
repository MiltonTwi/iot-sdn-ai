# Setup VM cloud para correr el lab — Oracle Cloud Free Tier

**Tiempo:** 30-45 min total. **Costo:** $0 (free tier permanente). **Resultado:** Linux nativo donde Mininet+OVS+Docker funciona sin pelear con WSL2.

---

## Por qué Oracle Cloud y no AWS/GCP

| Provider | Free permanente | Linux | RAM | Comentario |
|---|---|---|---|---|
| **Oracle Cloud** | **Sí, sin caducidad** | Ubuntu/Oracle Linux | hasta 24 GB ARM o 1 GB AMD64 | El más generoso |
| AWS | 12 meses | Amazon Linux | 1 GB t2.micro | Caduca, requiere tarjeta |
| GCP | $300 / 90 días | Ubuntu | hasta 4 GB e2-medium | Caduca |
| Azure | 12 meses | Ubuntu | 1 GB B1S | Caduca |

**Recomendación:** Oracle Cloud `VM.Standard.A1.Flex` ARM con 4 vCPU + 12 GB RAM (sigue siendo free). Linux ARM corre Mininet OK.

> Si prefieres AMD64: `VM.Standard.E2.1.Micro` también free (1 vCPU + 1 GB) — limitado para 67 hosts pero suficiente para una topo más pequeña.

---

## Paso 1 — Cuenta Oracle Cloud (15 min)

1. <https://www.oracle.com/cloud/free/>
2. Click "Start for free".
3. Llena formulario: nombre, email, país, idioma.
4. **Tarjeta de crédito**: necesaria para verificación. **No te cobra**. Si pasas free tier → te avisa, no cobra automático.
5. Verificación por SMS.
6. Espera email de "Account is provisioned" (~5-10 min).

---

## Paso 2 — Crear VM (10 min)

1. Login → Console.
2. **Menu hamburguesa → Compute → Instances**.
3. **Create Instance**:
   - Name: `iotsdn`
   - Image: **Ubuntu 24.04** (Canonical Ubuntu 24.04 Minimal)
   - Shape: click "Change shape" → **Ampere** (ARM) → `VM.Standard.A1.Flex` con **4 OCPU, 12 GB RAM**
   - Networking: usa default VCN (te crea uno auto)
   - SSH keys: **Generate SSH key pair** → descarga **ambas** (`.pub` y privada). Guarda la privada en `C:\Users\mquui\.ssh\oracle_iotsdn`.
4. Click **Create**.
5. Espera ~2 min hasta `RUNNING`.
6. Anota la **Public IP** (la mostrará en el detalle de la VM).

---

## Paso 3 — Conectar SSH (5 min)

```powershell
# desde tu PowerShell Windows
chmod 600 C:\Users\mquui\.ssh\oracle_iotsdn   # PowerShell ignora pero por costumbre
ssh -i C:\Users\mquui\.ssh\oracle_iotsdn ubuntu@<PUBLIC_IP>
```

Ya estás dentro de Ubuntu Linux REAL.

---

## Paso 4 — Setup del lab (15 min)

```bash
# en la VM (tras ssh)
sudo apt update
sudo apt install -y docker.io docker-compose-v2 git python3-pip python3-venv tcpdump
sudo usermod -aG docker ubuntu

# logout + login para que el grupo tome efecto
exit
ssh -i C:\Users\mquui\.ssh\oracle_iotsdn ubuntu@<PUBLIC_IP>

# verificar docker funciona
docker run --rm hello-world
# debe imprimir "Hello from Docker!"
```

---

## Paso 5 — Subir tu proyecto (5 min)

Opción A — `scp`:

```powershell
# desde Windows
cd C:\Users\mquui
scp -i .ssh\oracle_iotsdn -r iot-sdn-ai ubuntu@<PUBLIC_IP>:~/
```

(Va a tardar 1-2 min, 100+ MB de transferencia.)

Opción B — Git (más limpio, requiere repo en GitHub):

```bash
# en la VM
cd ~
git clone https://github.com/<tu-usuario>/<tu-repo>.git iot-sdn-ai
```

---

## Paso 6 — Abrir puertos para acceso desde el celular (5 min)

En Oracle Cloud Console:

1. **Networking → Virtual Cloud Networks → tu VCN → Subnets → Subnet → Security Lists → Default Security List**.
2. **Add Ingress Rules**:
   - Source: `0.0.0.0/0`
   - IP Protocol: TCP
   - Destination Port Range: `8000,8080,3000,9090`

3. En la VM:
```bash
sudo ufw allow 8000,8080,3000,9090/tcp
sudo ufw --force enable
```

---

## Paso 7 — Levantar el lab

```bash
cd ~/iot-sdn-ai

# Genera topología
python3 iot/topology/generate_topology.py

# Levanta stack (igual que en WSL)
docker compose -f SdnShare/docker-compose.yaml -f docker-compose.override.yaml --profile monitor up -d

# Espera ~30s
sleep 30

# Lanzar topología en mininet (esta vez SÍ va a funcionar)
docker exec -d sdnshare-mininet-1 bash -c "python3 /root/iot/topology/mn_iot_topo.py /root/iot/topology/network_config.iot.yaml controller --no-cli > /tmp/topo.log 2>&1"
sleep 30

# Test ping (en VM Linux pura, esto funciona al primer intento)
docker exec sdnshare-mininet-1 bash -c "
  ATK=\$(ps -ef | grep 'mininet:attacker' | grep -v grep | awk '{print \$2}' | head -1)
  nsenter -t \$ATK -n ping -c 3 10.10.0.12
"
```

Esperas: `0% packet loss`. ¡Eso es lo que no podías ver en WSL!

---

## Paso 8 — Captura real + ataques

```bash
# en la VM
docker cp ~/iot-sdn-ai/scripts/real_capture.sh sdnshare-mininet-1:/tmp/cap.sh 2>/dev/null
# o si no existe el script, copia el que está en /mnt/c/Users/mquui/AppData/Local/Temp/real_capture.sh

# (mejor usar el que dejé en docs/scripts/ — copia esos contenidos a un archivo nuevo)

# Lanza captura completa con 4 ataques
docker exec sdnshare-mininet-1 bash /tmp/cap.sh

# Procesa pipeline
RUN=$(cat /tmp/last_run.txt)
mkdir -p data/processed/$RUN
python3 iot/pipeline/flow_extractor.py --pcap data/raw/$RUN/capture.pcap --out data/processed/$RUN/flows.csv
python3 iot/pipeline/label_dataset.py --flows data/processed/$RUN/flows.csv --manifests data/raw/$RUN --out data/processed/$RUN/flows_labeled.csv
python3 iot/pipeline/feature_engineering.py --inp data/processed/$RUN/flows_labeled.csv --out data/processed/$RUN/dataset.csv

# Re-train con datos REALES
pip install --user --break-system-packages scikit-learn pandas joblib matplotlib shap xgboost
python3 ml_extra/train_all.py --dataset data/processed/$RUN/dataset.csv
python3 ml_extra/report.py --dataset data/processed/$RUN/dataset.csv

ls -la ml_extra/artifacts/report_$RUN.pdf
```

---

## Paso 9 — Acceso desde el celular

```
http://<PUBLIC_IP>:8000   # IoT dashboard
http://<PUBLIC_IP>:8080   # FlowManager
http://<PUBLIC_IP>:3000   # Grafana (admin/admin)
http://<PUBLIC_IP>:9090   # Prometheus
```

Funciona desde **cualquier red** (datos móviles, WiFi de cafetería, etc.) porque es internet pública.

---

## Paso 10 — Bajar resultados a tu Windows

```powershell
# desde Windows
scp -i C:\Users\mquui\.ssh\oracle_iotsdn ubuntu@<IP>:~/iot-sdn-ai/ml_extra/artifacts/* C:\Users\mquui\iot-sdn-ai\ml_extra\artifacts_real\
scp -i C:\Users\mquui\.ssh\oracle_iotsdn ubuntu@<IP>:~/iot-sdn-ai/data/processed/run_real_*/dataset.csv C:\Users\mquui\iot-sdn-ai\data\processed\real\
```

Ahora tienes el dataset real + modelos re-entrenados + PDF nuevo en tu Windows.

---

## Total tiempo invertido

| Paso | Tiempo |
|---|---|
| Crear cuenta + VM Oracle Cloud | 15 min |
| SSH + apt install | 15 min |
| Subir código | 5 min |
| Levantar lab + topo + captura + pipeline + train | 20 min |
| **Total** | **~55 min** |

---

## Después de la defensa

VM Oracle gratis se queda. Si la dejas corriendo, sigue gratis. Si quieres apagarla: Console → Stop. Si quieres borrarla: Console → Terminate. 

---

## Tradeoffs vs WSL local

| Aspecto | Oracle Cloud | WSL local |
|---|---|---|
| Mininet funciona | ✓ siempre | ✗ frágil |
| Latencia comandos | ~50ms (SSH) | ~5ms |
| Acceso al celular | ✓ desde cualquier red | requiere LAN o tunnel |
| Recursos | 4 vCPU 12 GB ARM | depende host |
| Caducidad | nunca free | nunca |
| Coste si pasas límites | $$ por hora | $0 |
| Dependencia de internet | ✓ requiere conexión | autónomo |
