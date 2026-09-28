# ═══════════════════════════════════════════════════════════
# SDN DDoS Detection Lab — Makefile
# ═══════════════════════════════════════════════════════════
.PHONY: help setup up down topo topo-clean sniff sniff-save monitor capture process train predict test lint clean

# Colores
CYAN  := \033[36m
GREEN := \033[32m
RESET := \033[0m

help: ## Muestra esta ayuda
	@echo ""
	@echo "$(CYAN)═══════ SDN DDoS Detection Lab ═══════$(RESET)"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  $(GREEN)%-15s$(RESET) %s\n", $$1, $$2}'
	@echo ""

# ─── Infraestructura ──────────────────────────────────────

setup: ## Levanta servicios base (controller + mininet)
	docker compose up -d controller mininet
	@echo "$(CYAN)⏳ Esperando a que el controller esté listo...$(RESET)"
	@until docker compose exec -T controller python3 -c "import socket; s=socket.socket(); s.settimeout(2); s.connect(('localhost',8080)); s.close()" 2>/dev/null; do sleep 2; done
	@echo "$(GREEN)✓ Lab SDN listo$(RESET)"
	@echo "  FlowManager: http://localhost:8080"

up: ## Levanta todos los servicios (infra + monitor)
	docker compose --profile monitor up -d
	@echo "$(CYAN)⏳ Esperando a que el controller esté listo...$(RESET)"
	@until docker compose exec -T controller python3 -c "import socket; s=socket.socket(); s.settimeout(2); s.connect(('localhost',8080)); s.close()" 2>/dev/null; do sleep 2; done
	@echo "$(GREEN)✓ Lab completo listo$(RESET)"
	@echo "  FlowManager: http://localhost:8080"
	@echo "  Grafana:     http://localhost:3000"
	@echo "  Prometheus:  http://localhost:9090"

down: ## Detiene todos los servicios
	docker compose --profile monitor down

restart: ## Reinicia controller + mininet (soluciona desconexiones)
	@echo "$(CYAN)🔄 Reiniciando controller...$(RESET)"
	docker compose restart controller
	@echo "$(CYAN)⏳ Esperando a que el controller esté listo...$(RESET)"
	@until docker compose exec -T controller python3 -c "import socket; s=socket.socket(); s.settimeout(2); s.connect(('localhost',8080)); s.close()" 2>/dev/null; do sleep 2; done
	docker compose exec -T mininet mn -c 2>/dev/null || true
	@echo "$(GREEN)✓ Controller listo — ejecuta 'make topo'$(RESET)"

topo: ## Inicia topología spine-leaf en Mininet
	@echo "$(CYAN)🧹 Limpiando topología anterior...$(RESET)"
	docker compose exec -T mininet mn -c 2>/dev/null || true
	@echo "$(CYAN)⏳ Verificando controller...$(RESET)"
	@until docker compose exec -T controller python3 -c "import socket; s=socket.socket(); s.settimeout(2); s.connect(('localhost',8080)); s.close()" 2>/dev/null; do sleep 2; done
	@echo "$(GREEN)✓ Controller listo — iniciando topología$(RESET)"
	docker compose exec -it mininet ./infra/topology/mn_spineleaf_topo.py infra/configs/network_config.yaml

topo-clean: ## Limpia topología Mininet
	docker compose exec -T mininet mn -c 2>/dev/null || true

# Interfaz a capturar (override: make sniff IFACE=s22-eth3)
IFACE ?= s21-eth3

sniff: ## Captura paquetes en vivo con tshark (IFACE=s21-eth3)
	@echo "$(CYAN)🦈 tshark en $(IFACE)$(RESET)"
	docker compose exec -T mininet tshark -l -i $(IFACE) \
		-T fields \
		-e frame.time_relative \
		-e ip.src -e ip.dst \
		-e ip.proto \
		-e tcp.srcport -e tcp.dstport \
		-e frame.len \
		-e tcp.flags.str \
		-E header=y -E separator=,

sniff-save: ## Captura a PCAP en data/raw/ (IFACE=s21-eth3)
	$(eval RUN := $(shell python3 scripts/generate_run_id.py --create-dir))
	@echo "$(CYAN)🦈 Capturando $(IFACE) → data/raw/$(RUN)/capture.pcap$(RESET)"
	docker compose exec -T mininet tshark -i $(IFACE) -w /root/scripts/../data/raw/$(RUN)/capture.pcap

monitor: ## Abre terminal tmux con monitor DDoS
	./open_terminal.sh

# ─── Pipeline de Datos ────────────────────────────────────

RUN_ID := $(shell python3 scripts/generate_run_id.py)

capture: ## Inicia captura de datos (genera run_id automático)
	@echo "$(CYAN)Run ID: $(RUN_ID)$(RESET)"
	python3 scripts/generate_run_id.py --create-dir
	@echo "$(GREEN)✓ Directorio de captura creado en data/raw/$(RUN_ID)$(RESET)"
	@echo "  Inicia la captura manualmente y guarda los datos en ese directorio"

# ─── ML (futuro) ──────────────────────────────────────────

train: ## Entrena modelo ML
	@echo "⚠️  Aún no implementado. Ver ml/train.py"

predict: ## Ejecuta inferencia
	@echo "⚠️  Aún no implementado. Ver ml/predict.py"

# ─── Calidad ──────────────────────────────────────────────

test: ## Ejecuta tests
	python3 -m pytest tests/ -v

lint: ## Ejecuta linter
	python3 -m ruff check .

# ─── Limpieza ─────────────────────────────────────────────

clean: ## Limpia datos temporales y cache Python
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@echo "$(GREEN)✓ Cache limpiado$(RESET)"
