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
        os_user="alleycat",
    )
    env = unit.env_file()
    assert "ALLEYCATV_PI_ID=pi-lobby-1" in env
    assert "ALLEYCATV_SERVER=http://alleycattv.local" in env
    assert "ALLEYCATV_MQTT=homeassistant.local" in env
    assert "ALLEYCATV_MQTT_PASS=secret" in env
    assert "ALLEYCATV_OS_USER=alleycat" in env
    # Membership must not be required
    assert "ALLEYCATV_BROADCAST_GROUP_ID=" in env


def test_user_data_enables_ssh_password():
    unit = UnitConfig(
        "pi-1",
        "pi-1",
        "http://x",
        "ha.local",
        os_user="alleycat",
        os_password="alleycat",
        os_password_hash="$6$saltexample$hash",
    )
    text = unit.user_data()
    assert text.startswith("#cloud-config\n")
    assert "enable_ssh: true" in text
    assert "ssh_pwauth: true" in text
    assert "name: alleycat" in text
    assert "plain_text_passwd:" in text
    assert "PasswordAuthentication yes" in text
    assert "alleycattv-firstboot.sh" in text


def test_env_adds_http_scheme():
    unit = UnitConfig("pi-1", "pi-1", "192.168.1.173", "ha.local")
    assert "ALLEYCATV_SERVER=http://192.168.1.173" in unit.env_file()


def test_wpa_optional():
    bare = UnitConfig("pi-1", "pi-1", "http://x", "ha.local")
    assert bare.wpa_supplicant() is None
    wifi = UnitConfig(
        "pi-1", "pi-1", "http://x", "ha.local", wifi_ssid="Alleycat", wifi_psk="pass"
    )
    text = wifi.wpa_supplicant()
    assert text is not None
    assert 'ssid="Alleycat"' in text


def test_network_config_wifi():
    wifi = UnitConfig(
        "pi-1",
        "pi-1",
        "http://x",
        "ha.local",
        wifi_ssid="NeoCore Networks",
        wifi_psk="secret",
    )
    text = wifi.network_config()
    assert "renderer: NetworkManager" in text
    assert '"NeoCore Networks"' in text
    assert 'password: "secret"' in text
    assert "eth0:" in text
    assert "route-metric: 100" in text
    assert "route-metric: 700" in text


def test_normalize_mqtt_strips_scheme():
    from config_render import normalize_mqtt_host

    assert normalize_mqtt_host("http://192.168.1.11") == "192.168.1.11"
    assert normalize_mqtt_host("192.168.1.11") == "192.168.1.11"


def test_userconf_requires_hash():
    unit = UnitConfig(
        "pi-1",
        "pi-1",
        "http://x",
        "ha.local",
        os_user="alleycat",
        os_password_hash="$6$saltexample$hash",
    )
    assert unit.userconf() == "alleycat:$6$saltexample$hash\n"


def test_sha512_crypt_openssl():
    from config_render import sha512_crypt

    hashed = sha512_crypt("alleycat")
    assert hashed.startswith("$6$")
    assert "alleycat" not in hashed


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
