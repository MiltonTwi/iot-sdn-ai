"""Tests para la política decide() del detector_service."""

from __future__ import annotations

from dashboard.detector_service import FAMILY_MAP, decide


def test_benign_no_action():
    assert decide("BENIGN", 0.99) is None


def test_ddos_high_confidence_drops():
    d = decide("SYN_FLOOD", 0.95)
    assert d is not None
    assert d["action"] == "drop"
    assert d["duration_s"] == 120


def test_amplification_high_confidence_drops():
    d = decide("DNS_AMPLIFICATION", 0.90)
    assert d["action"] == "drop"


def test_recon_medium_confidence_limits():
    d = decide("PORT_SCAN", 0.80)
    assert d["action"] == "limit"
    assert d["rate_kbps"] == 512


def test_low_confidence_no_action():
    assert decide("SYN_FLOOD", 0.60) is None


def test_protocol_abuse_limits():
    d = decide("MQTT_SUBSCRIBE_FLOOD", 0.80)
    assert d["action"] == "limit"


def test_bruteforce_limits():
    d = decide("CREDENTIAL_BRUTEFORCE", 0.80)
    assert d["action"] == "limit"


def test_mirai_drops():
    d = decide("MIRAI_COORDINATED", 0.90)
    assert d["action"] == "drop"


def test_family_map_covers_all_attack_labels():
    """Cada label en attacks/catalog.yaml debe estar mapeado."""
    import yaml
    from pathlib import Path
    cat = yaml.safe_load(Path("iot/attacks/catalog.yaml").read_text())
    labels = {s["label"] for s in cat["scenarios"]}
    missing = labels - set(FAMILY_MAP)
    assert not missing, f"labels sin family_map: {missing}"
