#!/bin/bash
# Reinicia el http_server del lab (host Mininet httpserve) sin tumbar la topología.
pkill -9 -f http_server.py; pkill -9 -f "http.server 80"; sleep 1
H=$(pgrep -f "is mininet:httpserve$" | head -1)
mnexec -a "$H" bash -c "nohup python3 /root/iot/devices/servers/http_server.py 80 >/tmp/http.log 2>&1 &"
sleep 2
P=$(pgrep -f "python3 /root/iot/devices/servers/http_server.py" | head -1)
echo "http_server pid=$P threads=$(ls /proc/$P/task | wc -l)"
A=$(pgrep -f "is mininet:attacker$" | head -1)
echo "GET desde attacker: $(mnexec -a "$A" curl -s -m 5 -o /dev/null -w '%{http_code}' http://10.10.0.12/)"
echo "threads contenedor: $(ps -eLf | wc -l)"
