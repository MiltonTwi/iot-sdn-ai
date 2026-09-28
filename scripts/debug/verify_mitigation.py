#!/usr/bin/env python3
"""Verifica mitigation chain end-to-end. Output: evidencia textual + JSON."""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path


def run(cmd, capture=True, timeout=30):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=capture, text=True, timeout=timeout)
        return r.returncode, r.stdout, r.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "TIMEOUT"


def main():
    print("=" * 70)
    print("MITIGATION CHAIN END-TO-END VERIFICATION")
    print("=" * 70)

    # 1. Find attacker host PID
    print("\n[1] Locate mininet:attacker host")
    rc, out, err = run("docker exec sdnshare-mininet-1 pgrep -fa 'mininet:attacker'")
    print(f"  rc={rc}")
    print(f"  stdout: {out.strip()}")
    if rc != 0 or not out.strip():
        print("FATAL: attacker host not found")
        sys.exit(1)
    pid_line = [l for l in out.split("\n") if "bash --norc" in l and "attacker" in l]
    if not pid_line:
        pid_line = [out.split("\n")[0]]
    pid = pid_line[0].split()[0]
    print(f"  attacker PID = {pid}")

    # 2. Ping test connectivity
    print("\n[2] Test connectivity (attacker → http_server)")
    rc, out, err = run(f"docker exec sdnshare-mininet-1 mnexec -a {pid} ping -c2 -W3 10.10.0.12")
    print(out[-300:] if out else err[-300:])

    # 3. Check OVS flows (baseline)
    print("\n[3] Baseline flows on spine_1 (before mitigation)")
    rc, out, _ = run("docker exec sdnshare-mininet-1 ovs-ofctl dump-flows s_spine_1 -O OpenFlow13 2>&1 | head -5")
    print(f"  rc={rc}")
    print(out[:400])

    # 4. POST /iot/mitigate to controller
    print("\n[4] POST /iot/mitigate to controller (DROP 10.10.0.99 for 60s)")
    curl_cmd = (
        "docker exec sdnshare-controller-1 curl -s -X POST http://localhost:8080/iot/mitigate "
        "-H 'Content-Type: application/json' "
        '-d \'{"src_ip":"10.10.0.99","action":"drop","duration_s":60}\''
    )
    rc, out, err = run(curl_cmd)
    print(f"  rc={rc}")
    print(f"  response: {out.strip()[:500]}")

    time.sleep(2)

    # 5. Verify DROP flow installed
    print("\n[5] OVS flows after mitigation (look for priority=200 drop)")
    rc, out, _ = run("docker exec sdnshare-mininet-1 ovs-ofctl dump-flows s_spine_1 -O OpenFlow13 2>&1")
    drop_flows = [l for l in out.split("\n") if "priority=200" in l or "actions=drop" in l]
    print(f"  found {len(drop_flows)} drop rules:")
    for f in drop_flows[:5]:
        print(f"    {f.strip()}")

    # 6. Status
    print("\n[6] GET /iot/status")
    rc, out, _ = run(
        "docker exec sdnshare-controller-1 curl -s http://localhost:8080/iot/status"
    )
    print(f"  {out.strip()[:500]}")

    # 7. Save evidence
    evidence = {
        "attacker_pid": pid,
        "post_mitigate_response": out.strip(),
        "drop_flows_found": len(drop_flows),
        "drop_flows_sample": drop_flows[:5],
    }
    Path("/home/ubuntu/iot-sdn-ai/ml_extra/artifacts/mitigation_evidence.json").write_text(json.dumps(evidence, indent=2))
    print("\nEvidence saved: mitigation_evidence.json")


if __name__ == "__main__":
    main()
