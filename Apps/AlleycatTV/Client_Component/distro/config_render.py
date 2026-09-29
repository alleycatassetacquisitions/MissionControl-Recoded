"""Render AlleycatTV per-unit boot/first-boot config artifacts."""
from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


def sha512_crypt(password: str) -> str:
    """Hash a password for Raspberry Pi OS userconf.txt (openssl passwd -6)."""
    openssl = shutil.which("openssl")
    if not openssl:
        for candidate in (
            Path(r"C:\Program Files\Git\usr\bin\openssl.exe"),
            Path(r"C:\Program Files\OpenSSL-Win64\bin\openssl.exe"),
        ):
            if candidate.is_file():
                openssl = str(candidate)
                break
    if not openssl:
        raise RuntimeError(
            "openssl not found (needed to hash the Pi OS password for userconf.txt). "
            "Install Git for Windows or OpenSSL, then retry."
        )
    completed = subprocess.run(
        [openssl, "passwd", "-6", "-stdin"],
        input=password + "\n",
        capture_output=True,
        text=True,
        check=False,
    )
    hashed = (completed.stdout or "").strip()
    if completed.returncode != 0 or not hashed.startswith("$6$"):
        err = (completed.stderr or "").strip() or f"exit {completed.returncode}"
        raise RuntimeError(f"openssl passwd -6 failed: {err}")
    return hashed


def normalize_server_url(url: str) -> str:
    """Ensure content server has an http(s) scheme."""
    u = (url or "").strip().rstrip("/")
    if u and "://" not in u:
        u = "http://" + u
    return u


def normalize_mqtt_host(host: str) -> str:
    """Strip accidental URL schemes from an MQTT broker host."""
    h = (host or "").strip()
    if "://" in h:
        h = h.split("://", 1)[1]
    return h.rstrip("/").split("/")[0]


def _yaml_quote(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


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
    wifi_country: str = "US"
    # Local Pi OS account (cloud-init user-data + legacy userconf.txt).
    os_user: str = "alleycat"
    os_password: str = "alleycat"
    os_password_hash: str = ""
    # Not membership — optional playlist key only; prefer blank (BGC assigns over MQTT).
    broadcast_group_id: str = ""

    def env_file(self) -> str:
        server = normalize_server_url(self.server_url)
        mqtt = normalize_mqtt_host(self.mqtt_host)
        lines = [
            f"ALLEYCATV_PI_ID={self.pi_id}",
            f"ALLEYCATV_BROADCAST_GROUP_ID={self.broadcast_group_id}",
            f"ALLEYCATV_SERVER={server}",
            f"ALLEYCATV_MQTT={mqtt}",
            f"ALLEYCATV_MQTT_PORT={self.mqtt_port}",
            f"ALLEYCATV_MQTT_USER={self.mqtt_user}",
            f"ALLEYCATV_MQTT_PASS={self.mqtt_pass}",
            f"ALLEYCATV_OS_USER={self.os_user}",
        ]
        return "\n".join(lines) + "\n"

    def userconf(self) -> str:
        """Legacy userconf.txt (kept as fallback beside cloud-init user-data)."""
        if not self.os_user or not self.os_password_hash:
            raise ValueError("os_user and os_password_hash are required for userconf.txt")
        return f"{self.os_user}:{self.os_password_hash}\n"

    def meta_data(self) -> str:
        """cloud-init meta-data (NoCloud)."""
        return (
            f"instance-id: alleycattv-{self.pi_id}\n"
            f"local-hostname: {self.hostname}\n"
        )

    def user_data(self) -> str:
        """cloud-init user-data for Trixie — user, SSH password auth, first-boot install."""
        if not self.os_user:
            raise ValueError("os_user is required for user-data")
        # Prefer plaintext for reliability on Pi OS cloud-init; hash is fallback.
        if not self.os_password and not self.os_password_hash:
            raise ValueError("os_password or os_password_hash is required for user-data")
        groups = (
            "users,adm,dialout,audio,netdev,video,plugdev,cdrom,"
            "games,input,gpio,spi,i2c,render,sudo"
        )
        if self.os_password:
            cred_line = f"    plain_text_passwd: {_yaml_quote(self.os_password)}\n"
        else:
            cred_line = f"    passwd: {_yaml_quote(self.os_password_hash)}\n"
        chpasswd = ""
        if self.os_password:
            chpasswd = (
                "chpasswd:\n"
                "  expire: false\n"
                "  list: |\n"
                f"    {self.os_user}:{self.os_password}\n"
            )
        return (
            "#cloud-config\n"
            f"hostname: {self.hostname}\n"
            "manage_etc_hosts: true\n"
            "timezone: America/Chicago\n"
            "users:\n"
            "  - default\n"
            f"  - name: {self.os_user}\n"
            f"    groups: {groups}\n"
            "    shell: /bin/bash\n"
            "    lock_passwd: false\n"
            f"{cred_line}"
            "    sudo: ALL=(ALL) NOPASSWD:ALL\n"
            f"{chpasswd}"
            "enable_ssh: true\n"
            "ssh_pwauth: true\n"
            "runcmd:\n"
            "  - [systemctl, enable, --now, ssh]\n"
            "  - [bash, -lc, 'sed -i \"s/^#\\?PasswordAuthentication.*/PasswordAuthentication yes/\" /etc/ssh/sshd_config.d/*.conf /etc/ssh/sshd_config 2>/dev/null; systemctl reload ssh || systemctl restart ssh']\n"
            "  - [bash, /boot/firmware/alleycattv-firstboot.sh]\n"
        )

    def network_config(self) -> str:
        """cloud-init network-config (Netplan v2) for Raspberry Pi OS Trixie+.

        Wi-Fi is preferred over Ethernet when both are up (lower DHCP route metric).
        """
        lines = [
            "network:",
            "  version: 2",
            "  renderer: NetworkManager",
            "  ethernets:",
            "    eth0:",
            "      dhcp4: true",
            "      optional: true",
            # Higher metric = lower priority vs Wi-Fi.
            "      dhcp4-overrides:",
            "        route-metric: 700",
        ]
        if self.wifi_ssid:
            lines += [
                "  wifis:",
                "    wlan0:",
                "      dhcp4: true",
                f"      regulatory-domain: {_yaml_quote(self.wifi_country)}",
                "      access-points:",
                f"        {_yaml_quote(self.wifi_ssid)}:",
                f"          password: {_yaml_quote(self.wifi_psk)}",
                "      optional: true",
                "      dhcp4-overrides:",
                "        route-metric: 100",
            ]
        return "\n".join(lines) + "\n"

    def wpa_supplicant(self) -> str | None:
        """Legacy Bookworm-era helper; Trixie ignores this — prefer network_config()."""
        if not self.wifi_ssid:
            return None
        psk = self.wifi_psk.replace('"', '\\"')
        ssid = self.wifi_ssid.replace('"', '\\"')
        return (
            "ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev\n"
            "update_config=1\n"
            f"country={self.wifi_country}\n\n"
            "network={\n"
            f'    ssid="{ssid}"\n'
            f'    psk="{psk}"\n'
            "}\n"
        )

    def firstboot_script(self) -> str:
        """Install AlleycatTV player from bootfs bundle (idempotent)."""
        return r"""#!/bin/bash
set -euo pipefail
BOOT=/boot/firmware
if [[ ! -d "$BOOT" ]]; then
  BOOT=/boot
fi
LOG=/var/log/alleycattv-firstboot.log
exec >>"$LOG" 2>&1
echo "=== alleycattv firstboot $(date -Is) ==="

install -m 640 "$BOOT/alleycattv.env" /etc/alleycattv.env || true
if [[ -f "$BOOT/alleycattv-hostname.txt" ]]; then
  hostnamectl set-hostname "$(tr -d '\r\n' < "$BOOT/alleycattv-hostname.txt")" || true
fi

MARKER=/var/lib/alleycattv/.player-installed
if [[ -f "$MARKER" ]] && systemctl is-enabled alleycattv-player >/dev/null 2>&1; then
  systemctl restart alleycattv-player || true
  echo "Player already installed; restarted."
  exit 0
fi

TGZ="$BOOT/alleycattv-client.tgz"
if [[ ! -f "$TGZ" ]]; then
  echo "Missing $TGZ — player not bundled on this card."
  exit 1
fi

rm -rf /opt/alleycattv-src
mkdir -p /opt/alleycattv-src
tar -xzf "$TGZ" -C /opt/alleycattv-src
chmod +x /opt/alleycattv-src/install.sh
/opt/alleycattv-src/install.sh --from-env
mkdir -p /var/lib/alleycattv
touch "$MARKER"
echo "Player install finished."
"""


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
    os_user: str = "alleycat"
    os_password: str = "alleycat"
    flashed: list[str] = field(default_factory=list)
