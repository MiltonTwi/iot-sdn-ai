

python3 - <<'EOF'

import json, urllib.request, base64
creds = base64.b64encode(b'admin:admin').decode()
headers = {'Authorization': f'Basic {creds}', 'Content-Type': 'application/json'}

def get_uid(name):
    req = urllib.request.Request(f'http://localhost:3000/api/datasources/name/{name}', headers=headers)
    return json.loads(urllib.request.urlopen(req).read())['uid']

uid_prom  = get_uid('prometheus')
uid_graph = get_uid('graphite')
uid_infl  = get_uid('influxdb')
print(f"Prometheus: {uid_prom} | Graphite: {uid_graph} | InfluxDB: {uid_infl}")

with open('/home/jose/Desktop/SdnCompartido/conf/metrics-dashboard.json') as f:
    content = f.read()

content = content.replace('cfefc64p8nzlsa', uid_prom)
content = content.replace('bfefc8vr7pm9sb', uid_graph)
content = content.replace('afefcai2avuv4e', uid_infl)

dashboard = json.loads(content)
dashboard.pop('id', None)
dashboard['uid'] = 'sdnshare-allmetrics'

payload = json.dumps({'dashboard': dashboard, 'overwrite': True, 'folderId': 0}).encode()
req = urllib.request.Request('http://localhost:3000/api/dashboards/db', data=payload, headers=headers)
result = json.loads(urllib.request.urlopen(req).read())
print(f"Dashboard: http://localhost:3000{result['url']}")

EOF


python3 -c "
import json

with open('/home/jose/Desktop/SdnCompartido/conf/metrics-dashboard.json', 'r') as f:
    content = f.read()

content = content.replace('edqgha3zfvzeod', 'cfedi8feiz280e')
content = content.replace('fdqgojaklqqyoa', 'bfedid5bftp8ge')
content = content.replace('edqgqekbjt2bkb', 'bfedifzzykagwe')

dashboard = json.loads(content)
dashboard.pop('id', None)
dashboard['uid'] = 'sdnshare-allmetrics'

payload = {'dashboard': dashboard, 'overwrite': True, 'folderId': 0}

with open('/tmp/dashboard_fixed.json', 'w') as f:
    json.dump(payload, f)
print('OK - archivo generado:', len(json.dumps(payload)), 'bytes')
"