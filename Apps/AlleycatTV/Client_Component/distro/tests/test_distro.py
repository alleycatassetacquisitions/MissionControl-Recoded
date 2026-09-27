"""Tests for AlleycatTV distro config render + drive safety (no disk I/O)."""
from __future__ import annotations

import sys
from pathlib import Path

_DISTRO = Path(__file__).resolve().parent.parent
if str(_DISTRO) not in sys.path:
    sys.path.insert(0, str(_DISTRO))

from config_render import UnitConfig
from drives import DriveInfo, is_safe_flash_target


def test_env_file_contains_pi_and_mqtt():
    unit = UnitConfig(
        pi_id="pi-lobby-1",
        hostname="pi-lobby-1",
        server_url="http://alleycattv.local/",
        mqtt_host="homeassistant.local",
        mqtt_user="mqtt",
        mqtt_pass="secret",
    )
    env = unit.env_file()
    assert "ALLEYCATV_PI_ID=pi-lobby-1" in env
    assert "ALLEYCATV_SERVER=http://alleycattv.local" in env
    assert "ALLEYCATV_MQTT=homeassistant.local" in env
    assert "ALLEYCATV_MQTT_PASS=secret" in env
    # Membership must not be required
    assert "ALLEYCATV_BROADCAST_GROUP_ID=" in env


def test_wpa_optional():
    bare = UnitConfig("pi-1", "pi-1", "http://x", "ha.local")
    assert bare.wpa_supplicant() is None
    wifi = UnitConfig(
        "pi-1", "pi-1", "http://x", "ha.local", wifi_ssid="Alleycat", wifi_psk="pass"
    )
    text = wifi.wpa_supplicant()
    assert text is not None
    assert 'ssid="Alleycat"' in text


def test_refuse_system_disk():
    ok, reason = is_safe_flash_target(
        DriveInfo(r"\\.\PHYSICALDRIVE0", "NVMe", 512_000_000_000, "NVMe")
    )
    assert ok is False
    assert (
        "PHYSICALDRIVE0" in reason
        or "NVMe" in reason
        or "too large" in reason
        or "system disk" in reason
    )


def test_accept_typical_sd():
    ok, reason = is_safe_flash_target(
        DriveInfo(r"\\.\PHYSICALDRIVE3", "USB SD Reader", 32_000_000_000, "USB")
    )
    assert ok is True
    assert reason == "ok"


def test_refuse_tiny_drive():
    ok, _ = is_safe_flash_target(
        DriveInfo(r"\\.\PHYSICALDRIVE2", "Tiny", 1_000_000_000, "USB")
    )
    assert ok is False
