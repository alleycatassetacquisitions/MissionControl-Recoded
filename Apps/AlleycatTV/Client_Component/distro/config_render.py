"""Render AlleycatTV per-unit boot/first-boot config artifacts."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class UnitConfig:
    pi_id: str
    hostname: str
    server_url: str
    mqtt_host: str
    mqtt_port: int = 1883
    mqtt_user: str = ""
    mqtt_pass: str = ""
    wifi_ssid: str = ""
    wifi_psk: str = ""
    # Not membership — optional playlist key only; prefer blank until Phase 7.
    broadcast_group_id: str = ""

    def env_file(self) -> str:
        lines = [
            f"ALLEYCATV_PI_ID={self.pi_id}",
            f"ALLEYCATV_BROADCAST_GROUP_ID={self.broadcast_group_id}",
            f"ALLEYCATV_SERVER={self.server_url.rstrip('/')}",
            f"ALLEYCATV_MQTT={self.mqtt_host}",
            f"ALLEYCATV_MQTT_PORT={self.mqtt_port}",
            f"ALLEYCATV_MQTT_USER={self.mqtt_user}",
            f"ALLEYCATV_MQTT_PASS={self.mqtt_pass}",
        ]
        return "\n".join(lines) + "\n"

    def userconf(self) -> str:
        """Raspberry Pi OS userconf.txt style hostname hint (informational)."""
        return f"# AlleycatTV unit {self.pi_id} hostname={self.hostname}\n"

    def wpa_supplicant(self) -> str | None:
        if not self.wifi_ssid:
            return None
        psk = self.wifi_psk.replace('"', '\\"')
        ssid = self.wifi_ssid.replace('"', '\\"')
        return (
            "ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev\n"
            "update_config=1\n"
            "country=US\n\n"
            "network={\n"
            f'    ssid="{ssid}"\n'
            f'    psk="{psk}"\n'
            "}\n"
        )

    def firstboot_script(self) -> str:
        return (
            "#!/bin/bash\n"
            "set -euo pipefail\n"
            f"hostnamectl set-hostname {self.hostname!s} || true\n"
            "install -m 640 /boot/firmware/alleycattv.env /etc/alleycattv.env 2>/dev/null \\\n"
            "  || install -m 640 /boot/alleycattv.env /etc/alleycattv.env\n"
            "systemctl daemon-reload || true\n"
            "systemctl restart alleycattv-player || true\n"
        )


@dataclass
class SessionDefaults:
    """Venue defaults reused across cards in one flash session."""

    server_url: str = ""
    mqtt_host: str = ""
    mqtt_port: int = 1883
    mqtt_user: str = ""
    mqtt_pass: str = ""
    wifi_ssid: str = ""
    wifi_psk: str = ""
    flashed: list[str] = field(default_factory=list)
