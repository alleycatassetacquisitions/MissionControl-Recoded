"""AlleycatTV SD distro CLI — flash many TV Pi cards from a prep PC.

Workflow:
  1. Enter venue defaults once (content server + Mosquitto)
  2. Enter unit PI_ID / hostname (optional Wi-Fi)
  3. Select SD drive (safety guards refuse system disks)
  4. Write base image + inject alleycattv.env onto boot partition
  5. Eject → insert next card → repeat

Usage (from this directory, admin/elevated recommended for raw disk write):

  python flash.py --image path\\to\\raspios-lite.img
  python flash.py --image path\\to\\raspios-lite.img --dry-run
"""
from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from config_render import SessionDefaults, UnitConfig, normalize_mqtt_host, sha512_crypt
from drives import DriveInfo, is_safe_flash_target, list_removable_drives


def _prompt(label: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    value = input(f"{label}{suffix}: ").strip()
    return value or default


def _prompt_int(label: str, default: int) -> int:
    raw = _prompt(label, str(default))
    try:
        return int(raw)
    except ValueError:
        return default


def _choose_drive() -> DriveInfo | None:
    drives = list_removable_drives()
    if not drives:
        print("No removable drives detected. Insert an SD reader and retry.")
        return None
    print("\nDetected drives:")
    safe: list[DriveInfo] = []
    for i, d in enumerate(drives):
        ok, reason = is_safe_flash_target(d)
        mark = "OK" if ok else f"BLOCKED ({reason})"
        print(f"  [{i}] {d.device_id}  {d.label}  {d.size_gb:.1f} GiB  {d.bus}  - {mark}")
        if ok:
            safe.append(d)
    if not safe:
        print("No safe flash targets. Refusing to continue.")
        return None
    raw = input("Select drive index: ").strip()
    try:
        idx = int(raw)
        chosen = drives[idx]
    except (ValueError, IndexError):
        print("Invalid selection.")
        return None
    ok, reason = is_safe_flash_target(chosen)
    if not ok:
        print(f"Refusing: {reason}")
        return None
    confirm = input(
        f"Type YES to erase and flash {chosen.device_id} ({chosen.size_gb:.1f} GiB): "
    ).strip()
    if confirm != "YES":
        print("Aborted.")
        return None
    return chosen


def _find_rpi_imager() -> Path | None:
    """Locate rpi-imager.exe (PATH first, then common Windows install dirs).

    Prefer the .exe over rpi-imager-cli.cmd — the vendor .cmd does not propagate
    Imager's non-zero exit codes, which made failed writes look like success.
    """
    for name in ("rpi-imager", "rpi-imager.exe"):
        found = shutil.which(name)
        if found:
            return Path(found)
    program_files = Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
    for relative in (
        Path("Raspberry Pi Ltd") / "Imager" / "rpi-imager.exe",
        Path("Raspberry Pi Imager") / "rpi-imager.exe",
    ):
        candidate = program_files / relative
        if candidate.is_file():
            return candidate
    return None


def _write_image_windows(image: Path, drive: DriveInfo, dry_run: bool) -> None:
    # Prefer Raspberry Pi Imager CLI if present; else dd via external tools is unsafe.
    rpi = _find_rpi_imager()
    if rpi:
        # Imager is a GUI subsystem app — start /WAIT so we do not inject before
        # the write finishes. --enable-writing-system-drives is required because
        # many USB SD readers present as fixed disks; our own drive picker already
        # refuses system / oversized targets.
        cmd = [
            "cmd",
            "/c",
            "start",
            "/WAIT",
            "",
            str(rpi),
            "--cli",
            "--enable-writing-system-drives",
            str(image.resolve()),
            drive.device_id,
        ]
        print("Running:", " ".join(cmd))
        if dry_run:
            return
        completed = subprocess.run(cmd, check=False)
        if completed.returncode != 0:
            raise RuntimeError(
                f"Raspberry Pi Imager failed (exit {completed.returncode}). "
                "Run an elevated PowerShell, confirm the SD is seated, and retry."
            )
        return
    # Fallback: PowerShell raw write is dangerous; require explicit tool
    raise RuntimeError(
        "Install Raspberry Pi Imager (rpi-imager --cli) or flash the base image "
        "manually, then re-run with --inject-only after mounting the boot partition."
    )


def _write_image_linux(image: Path, drive: DriveInfo, dry_run: bool) -> None:
    cmd = ["dd", f"if={image}", f"of={drive.device_id}", "bs=4M", "status=progress", "conv=fsync"]
    print("Running:", " ".join(cmd))
    if dry_run:
        return
    subprocess.check_call(cmd)


def _client_component_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _pack_client_bundle(boot_mount: Path) -> None:
    """Tar Client_Component onto bootfs for first-boot install.sh --from-env."""
    import tarfile

    client_root = _client_component_root()
    out = boot_mount / "alleycattv-client.tgz"
    skip_parts = {"__pycache__", ".git"}
    skip_suffixes = {".pyc", ".pyo", ".img", ".xz"}
    with tarfile.open(out, "w:gz") as tar:
        for path in client_root.rglob("*"):
            if not path.is_file():
                continue
            rel = path.relative_to(client_root)
            if any(part in skip_parts for part in rel.parts):
                continue
            if path.suffix.lower() in skip_suffixes:
                continue
            name = path.name.lower()
            if name.endswith(".img.xz") or name.endswith(".img"):
                continue
            tar.add(path, arcname=str(rel).replace("\\", "/"))
    print(f"Bundled player sources -> {out} ({out.stat().st_size // 1024} KiB)")


def _inject_boot_config(unit: UnitConfig, boot_mount: Path) -> None:
    boot_mount.mkdir(parents=True, exist_ok=True)
    # Trixie cloud-init (authoritative for user/SSH) + legacy userconf/ssh fallbacks.
    (boot_mount / "user-data").write_text(unit.user_data(), encoding="utf-8", newline="\n")
    (boot_mount / "meta-data").write_text(unit.meta_data(), encoding="utf-8", newline="\n")
    (boot_mount / "userconf.txt").write_text(unit.userconf(), encoding="utf-8", newline="\n")
    (boot_mount / "ssh").write_text("", encoding="utf-8")
    (boot_mount / "alleycattv.env").write_text(unit.env_file(), encoding="utf-8", newline="\n")
    (boot_mount / "alleycattv-hostname.txt").write_text(
        unit.hostname + "\n", encoding="utf-8", newline="\n"
    )
    (boot_mount / "network-config").write_text(
        unit.network_config(), encoding="utf-8", newline="\n"
    )
    script = boot_mount / "alleycattv-firstboot.sh"
    script.write_text(unit.firstboot_script(), encoding="utf-8", newline="\n")
    _pack_client_bundle(boot_mount)
    print(f"Injected config for {unit.pi_id} into {boot_mount}")


def _find_boot_mount_hint() -> Path | None:
    """Try common Windows/Linux boot mount points after imaging."""
    candidates: list[Path] = []
    if platform.system() == "Windows":
        # Volume label is the most reliable signal after Imager remounts.
        try:
            ps = (
                "Get-Volume | Where-Object { "
                "$_.FileSystemLabel -match '^(bootfs|boot)$' "
                "-and $_.DriveLetter } | "
                "Select-Object -ExpandProperty DriveLetter"
            )
            out = subprocess.check_output(
                ["powershell", "-NoProfile", "-Command", ps],
                text=True,
                stderr=subprocess.DEVNULL,
            )
            for letter in out.split():
                letter = letter.strip()
                if letter:
                    candidates.append(Path(f"{letter}:/"))
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass
        # Include D: — USB readers often land there after Imager remounts.
        for letter in "DEFGHIJKLMNOPQRSTUVWXYZ":
            p = Path(f"{letter}:/")
            if p.exists() and (
                (p / "cmdline.txt").exists()
                or (p / "config.txt").exists()
                or (p / "firmware").exists()
            ):
                candidates.append(p)
    else:
        for p in (Path("/media"), Path("/mnt"), Path("/run/media")):
            if not p.exists():
                continue
            for child in p.rglob("cmdline.txt"):
                candidates.append(child.parent)
    # Prefer mounts that look like a real Pi bootfs.
    for p in candidates:
        if p.exists() and ((p / "cmdline.txt").exists() or (p / "config.txt").exists()):
            return p
    return candidates[0] if candidates else None


def _wait_for_boot_mount(*, timeout_sec: float = 90.0) -> Path | None:
    """Poll until Windows remounts bootfs after Imager finishes."""
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        boot = _find_boot_mount_hint()
        if boot is not None:
            return boot
        time.sleep(2.0)
    return None


def flash_one(
    *,
    image: Path | None,
    defaults: SessionDefaults,
    dry_run: bool,
    inject_only: bool,
) -> bool:
    pi_id = _prompt("Pi ID (e.g. pi-lobby-1)")
    if not pi_id:
        print("Pi ID required.")
        return False
    hostname = _prompt("Hostname", pi_id)
    wifi_ssid = _prompt("Wi-Fi SSID (required for headless TV Pis)", defaults.wifi_ssid)
    wifi_psk = ""
    if wifi_ssid:
        wifi_psk = _prompt("Wi-Fi PSK", defaults.wifi_psk)
    else:
        print("WARNING: no Wi-Fi SSID - Pi will only come online if Ethernet is plugged in.")

    unit = UnitConfig(
        pi_id=pi_id,
        hostname=hostname,
        server_url=defaults.server_url,
        mqtt_host=defaults.mqtt_host,
        mqtt_port=defaults.mqtt_port,
        mqtt_user=defaults.mqtt_user,
        mqtt_pass=defaults.mqtt_pass,
        wifi_ssid=wifi_ssid,
        wifi_psk=wifi_psk,
        os_user=defaults.os_user,
        os_password=defaults.os_password,
        os_password_hash=sha512_crypt(defaults.os_password),
    )
    defaults.wifi_ssid = wifi_ssid
    defaults.wifi_psk = wifi_psk

    if dry_run:
        print("--- dry-run env ---")
        print(unit.env_file())
        print("--- network-config ---")
        print(unit.network_config())
        if not inject_only:
            drive = _choose_drive()
            if drive and image:
                print(f"Would write {image} -> {drive.device_id}")
        defaults.flashed.append(pi_id)
        return True

    if not inject_only:
        if image is None or not image.exists():
            print("Image path required unless --inject-only.")
            return False
        drive = _choose_drive()
        if drive is None:
            return False
        if platform.system() == "Windows":
            _write_image_windows(image, drive, dry_run=False)
        else:
            _write_image_linux(image, drive, dry_run=False)
        print("Waiting for boot partition to remount (up to 90s)...")
        boot = _wait_for_boot_mount(timeout_sec=90.0)
    else:
        boot = _find_boot_mount_hint()

    if boot is None:
        raw = _prompt("Boot partition mount path (e.g. D:\\ or E:\\)")
        boot = Path(raw) if raw else None
    if boot is None or not boot.exists():
        staging = Path(tempfile.mkdtemp(prefix="alleycattv-flash-"))
        _inject_boot_config(unit, staging)
        print(f"Could not find boot mount - files staged at {staging}")
        if not inject_only:
            print(
                "Image may be written, but config was NOT injected onto the card. "
                "Re-insert the SD until bootfs appears, then run: "
                "py -3 flash.py --inject-only"
            )
            return False
        print("Copy alleycattv.env onto the SD boot partition, then eject.")
        return False
    _inject_boot_config(unit, boot)

    defaults.flashed.append(pi_id)
    print(f"Done: {pi_id}. Safely eject the SD card, insert the next, press Enter.")
    print("Do not power the Pi until eject completes - first boot must see network-config.")
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AlleycatTV SD distro / flash tool")
    parser.add_argument(
        "--image",
        type=Path,
        help="Path to Raspberry Pi OS Lite (64-bit) .img / .img.xz",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print config and drive choice only — no disk writes",
    )
    parser.add_argument(
        "--inject-only",
        action="store_true",
        help="Skip image write; only inject alleycattv.env onto mounted boot",
    )
    args = parser.parse_args(argv)

    print("AlleycatTV distro - venue defaults (reused for each card)")
    defaults = SessionDefaults(
        server_url=_prompt("Content server URL", os.getenv("ALLEYCATV_SERVER", "")),
        mqtt_host=normalize_mqtt_host(
            _prompt(
                "MQTT broker (HAOS Mosquitto host, no http://)",
                os.getenv("ALLEYCATV_MQTT", "homeassistant.local"),
            )
        ),
        mqtt_port=_prompt_int("MQTT port", 1883),
        mqtt_user=_prompt("MQTT username", ""),
        mqtt_pass=_prompt("MQTT password", ""),
        os_user=_prompt("Pi OS username", os.getenv("ALLEYCATV_OS_USER", "alleycat")),
        os_password=_prompt(
            "Pi OS password", os.getenv("ALLEYCATV_OS_PASSWORD", "alleycat")
        ),
    )
    if not defaults.server_url:
        print("Content server URL is required.")
        return 2

    while True:
        ok = flash_one(
            image=args.image,
            defaults=defaults,
            dry_run=args.dry_run,
            inject_only=args.inject_only,
        )
        if not ok:
            again = input("Retry this card? [y/N]: ").strip().lower()
            if again != "y":
                break
            continue
        nxt = input("Flash another card? [Y/n]: ").strip().lower()
        if nxt == "n":
            break

    print(f"Session complete. Flashed: {', '.join(defaults.flashed) or '(none)'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
