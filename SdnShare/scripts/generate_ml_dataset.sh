#!/bin/bash

# Configuración
OUTPUT_FILE="dataset_ddos_$(date +%Y%m%d_%H%M%S).csv"
INTERVAL=2  # Segundos entre capturas
LABEL="NORMAL"  # Cambiar manualmente a "ATTACK" durante ataques

echo "🤖 Generador de Dataset para ML - Detección DDoS"
echo "================================================"
echo ""
echo "Archivo de salida: $OUTPUT_FILE"
echo "Intervalo: ${INTERVAL}s"
echo "Etiqueta actual: $LABEL"
echo ""
echo "⚠️  IMPORTANTE: Cambia la variable LABEL a 'ATTACK' cuando inicies un ataque"
echo ""

# Crear archivo CSV con headers
cat > "$OUTPUT_FILE" << EOF
timestamp,switch,port,host,rx_pkts,tx_pkts,rx_bytes,tx_bytes,drops,errors,collisions,rx_pps,tx_pps,rx_bps,tx_bps,avg_packet_size_rx,avg_packet_size_tx,rx_tx_ratio,label
EOF

# Arrays para almacenar valores previos
declare -A prev_rx_pkts
declare -A prev_tx_pkts
declare -A prev_rx_bytes
declare -A prev_tx_bytes

# Mapeo de puertos a hosts
declare -A port_to_host
port_to_host["s21-3"]="h1"
port_to_host["s21-4"]="h2"
port_to_host["s22-3"]="h3"
port_to_host["s22-4"]="h4"
port_to_host["s23-3"]="h5"
port_to_host["s23-4"]="h6"

# Inicializar valores previos
echo "Inicializando..."
for switch in s21 s22 s23; do
    for port in 3 4; do
        key="${switch}-${port}"
        
        # Obtener datos del puerto
        port_data=$(docker compose exec -T mininet ovs-ofctl dump-ports $switch 2>/dev/null | grep -A 1 "port  $port:")
        
        rx_pkts=$(echo "$port_data" | head -1 | grep -o 'rx pkts=[0-9]*' | cut -d'=' -f2)
        tx_pkts=$(echo "$port_data" | tail -1 | grep -o 'tx pkts=[0-9]*' | cut -d'=' -f2)
        rx_bytes=$(echo "$port_data" | head -1 | grep -o 'bytes=[0-9]*' | head -1 | cut -d'=' -f2)
        tx_bytes=$(echo "$port_data" | tail -1 | grep -o 'bytes=[0-9]*' | head -1 | cut -d'=' -f2)
        
        prev_rx_pkts[$key]=${rx_pkts:-0}
        prev_tx_pkts[$key]=${tx_pkts:-0}
        prev_rx_bytes[$key]=${rx_bytes:-0}
        prev_tx_bytes[$key]=${tx_bytes:-0}
    done
done

echo "✓ Inicialización completa"
echo "📊 Capturando datos..."
echo ""

# Loop principal de captura
while true; do
    timestamp=$(date +%Y-%m-%d\ %H:%M:%S)
    
    for switch in s21 s22 s23; do
        for port in 3 4; do
            key="${switch}-${port}"
            host="${port_to_host[$key]}"
            
            # Obtener datos actuales
            port_data=$(docker compose exec -T mininet ovs-ofctl dump-ports $switch 2>/dev/null | grep -A 1 "port  $port:")
            
            rx_pkts=$(echo "$port_data" | head -1 | grep -o 'rx pkts=[0-9]*' | cut -d'=' -f2)
            tx_pkts=$(echo "$port_data" | tail -1 | grep -o 'tx pkts=[0-9]*' | cut -d'=' -f2)
            rx_bytes=$(echo "$port_data" | head -1 | grep -o 'bytes=[0-9]*' | head -1 | cut -d'=' -f2)
            tx_bytes=$(echo "$port_data" | tail -1 | grep -o 'bytes=[0-9]*' | head -1 | cut -d'=' -f2)
            drops=$(echo "$port_data" | head -1 | grep -o 'drop=[0-9]*' | cut -d'=' -f2)
            errors=$(echo "$port_data" | head -1 | grep -o 'errs=[0-9]*' | cut -d'=' -f2)
            collisions=$(echo "$port_data" | tail -1 | grep -o 'coll=[0-9]*' | cut -d'=' -f2)
            
            # Validar números
            rx_pkts=${rx_pkts:-0}
            tx_pkts=${tx_pkts:-0}
            rx_bytes=${rx_bytes:-0}
            tx_bytes=${tx_bytes:-0}
            drops=${drops:-0}
            errors=${errors:-0}
            collisions=${collisions:-0}
            
            # Calcular deltas
            prev_rx=${prev_rx_pkts[$key]:-0}
            prev_tx=${prev_tx_pkts[$key]:-0}
            prev_rx_b=${prev_rx_bytes[$key]:-0}
            prev_tx_b=${prev_tx_bytes[$key]:-0}
            
            delta_rx_pkts=$((rx_pkts - prev_rx))
            delta_tx_pkts=$((tx_pkts - prev_tx))
            delta_rx_bytes=$((rx_bytes - prev_rx_b))
            delta_tx_bytes=$((tx_bytes - prev_tx_b))
            
            # Evitar negativos
            [ $delta_rx_pkts -lt 0 ] && delta_rx_pkts=0
            [ $delta_tx_pkts -lt 0 ] && delta_tx_pkts=0
            [ $delta_rx_bytes -lt 0 ] && delta_rx_bytes=0
            [ $delta_tx_bytes -lt 0 ] && delta_tx_bytes=0
            
            # Calcular features
            rx_pps=$((delta_rx_pkts / INTERVAL))
            tx_pps=$((delta_tx_pkts / INTERVAL))
            rx_bps=$((delta_rx_bytes / INTERVAL))
            tx_bps=$((delta_tx_bytes / INTERVAL))
            
            # Tamaño promedio de paquete (evitar división por cero)
            if [ $delta_rx_pkts -gt 0 ]; then
                avg_pkt_size_rx=$((delta_rx_bytes / delta_rx_pkts))
            else
                avg_pkt_size_rx=0
            fi
            
            if [ $delta_tx_pkts -gt 0 ]; then
                avg_pkt_size_tx=$((delta_tx_bytes / delta_tx_pkts))
            else
                avg_pkt_size_tx=0
            fi
            
            # Ratio RX/TX (evitar división por cero)
            if [ $tx_pps -gt 0 ]; then
                rx_tx_ratio=$(echo "scale=2; $rx_pps / $tx_pps" | bc)
            else
                rx_tx_ratio=0
            fi
            
            # Escribir al CSV
            echo "$timestamp,$switch,$port,$host,$rx_pkts,$tx_pkts,$rx_bytes,$tx_bytes,$drops,$errors,$collisions,$rx_pps,$tx_pps,$rx_bps,$tx_bps,$avg_pkt_size_rx,$avg_pkt_size_tx,$rx_tx_ratio,$LABEL" >> "$OUTPUT_FILE"
            
            # Actualizar valores previos
            prev_rx_pkts[$key]=$rx_pkts
            prev_tx_pkts[$key]=$tx_pkts
            prev_rx_bytes[$key]=$rx_bytes
            prev_tx_bytes[$key]=$tx_bytes
        done
    done
    
    echo "[$(date +%H:%M:%S)] Captura registrada - Label: $LABEL"
    sleep $INTERVAL
done