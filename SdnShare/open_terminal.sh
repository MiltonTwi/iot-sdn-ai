#!/bin/bash

echo "🚀 Iniciando lab DDoS con tmux..."

# Crear sesión tmux
tmux new-session -d -s ddos_lab

# Panel 0: Monitor
tmux send-keys -t ddos_lab:0 'cd ~/Desktop/SdnShare&& ./infra/monitoring/pk_monitor.sh' C-m

# Panel 1: Mininet
tmux split-window -v -t ddos_lab:0
tmux send-keys -t ddos_lab:0.1 'cd ~/Desktop/SdnShare && docker compose exec -it mininet ./infra/topology/mn_spineleaf_topo.py infra/configs/network_config.yaml' C-m

# Panel 2: Comandos de ataque (espera a que mininet inicie)
tmux split-window -h -t ddos_lab:0.0 \; set-option -g mouse on

# Adjuntar a la sesión
tmux attach-session -t ddos_lab