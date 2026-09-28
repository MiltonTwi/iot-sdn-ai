#!/bin/bash

# Colores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'
 


 
# Arrays para almacenar valores previos
declare -A prev_rx
declare -A prev_tx

# Función CORREGIDA para obtener stats de hosts
get_host_stats() {
    local host=$1
    
    # Mapear host a switch y puerto
    case $host in
        h1) switch="s21"; port="3";;
        h2) switch="s21"; port="4";;
        h3) switch="s22"; port="3";;
        h4) switch="s22"; port="4";;
        h5) switch="s23"; port="3";;
        h6) switch="s23"; port="4";;
    esac
    
    # Obtener datos del puerto completo
    local port_data=$(docker compose exec -T mininet ovs-ofctl dump-ports $switch 2>/dev/null | grep -A 1 "port  $port:")
    
    # Extraer RX packets (primera línea)
    local switch_rx=$(echo "$port_data" | head -1 | grep -o 'rx pkts=[0-9]*' | cut -d'=' -f2)
    
    # Extraer TX packets (segunda línea)  
    local switch_tx=$(echo "$port_data" | tail -1 | grep -o 'tx pkts=[0-9]*' | cut -d'=' -f2)
    
    # Para el host: lo que el switch TX es lo que el host RX, y viceversa
    echo "${switch_tx:-0} ${switch_rx:-0}"
}

# Inicializar
clear
echo -e "${CYAN}╔════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║     Monitor de Tráfico DDoS - SDN Lab     ║${NC}"
echo -e "${CYAN}╚════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${BLUE}Inicializando monitor basado en hosts...${NC}"

for host in h1 h2 h3 h4 h5 h6; do
    stats=($(get_host_stats $host))
    prev_rx[$host]=${stats[0]:-0}
    prev_tx[$host]=${stats[1]:-0}
    printf "  %-4s RX=%-8d TX=%-8d\n" "$host:" "${prev_rx[$host]}" "${prev_tx[$host]}"
done

echo ""
echo -e "${GREEN}✓ Monitor iniciado - Presiona Ctrl+C para detener${NC}"
echo ""
sleep 2

# Loop principal
while true; do
    sleep 2
    
    echo -e "${YELLOW}[$(date +%H:%M:%S)]${NC} ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    for host in h1 h2 h3 h4 h5 h6; do
        stats=($(get_host_stats $host))
        rx=${stats[0]:-0}
        tx=${stats[1]:-0}
        
        # Validar que sean números
        if ! [[ "$rx" =~ ^[0-9]+$ ]]; then rx=0; fi
        if ! [[ "$tx" =~ ^[0-9]+$ ]]; then tx=0; fi
        
        # Calcular diferencia
        prev_rx_val=${prev_rx[$host]:-0}
        prev_tx_val=${prev_tx[$host]:-0}
        
        rx_diff=$(( (rx - prev_rx_val) / 2 ))
        tx_diff=$(( (tx - prev_tx_val) / 2 ))
        
        # Evitar negativos
        if [ $rx_diff -lt 0 ]; then rx_diff=0; fi
        if [ $tx_diff -lt 0 ]; then tx_diff=0; fi
        
        # Determinar estado y mostrar
        if [ $rx_diff -gt 500 ] || [ $tx_diff -gt 500 ]; then
            printf "${RED}⚠️  %-4s RX=%6d pps, TX=%6d pps [ANOMALÍA DETECTADA]${NC}\n" "$host:" "$rx_diff" "$tx_diff"
        elif [ $rx_diff -gt 100 ] || [ $tx_diff -gt 100 ]; then
            printf "${YELLOW}⚡ %-4s RX=%6d pps, TX=%6d pps [Tráfico elevado]${NC}\n" "$host:" "$rx_diff" "$tx_diff"
        else
            printf "${GREEN}✓  %-4s RX=%6d pps, TX=%6d pps${NC}\n" "$host:" "$rx_diff" "$tx_diff"
        fi
        
        prev_rx[$host]=$rx
        prev_tx[$host]=$tx
    done
    echo ""
done