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

from config_render import SessionDefaults, UnitConfig
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
        print(f"  [{i}] {d.device_id}  {d.label}  {d.size_gb:.1f} GiB  {d.bus}  — {mark}")
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


def _write_image_windows(image: Path, drive: DriveInfo, dry_run: bool) -> None:
    # Prefer Raspberry Pi Imager CLI if present; else dd via external tools is unsafe.
    rpi = shutil.which("rpi-imager") or shutil.which("rpi-imager.exe")
    if rpi:
        cmd = [rpi, "--cli", str(image), drive.device_id]
        print("Running:", " ".join(cmd))
        if dry_run:
            return
        subprocess.check_call(cmd)
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


def _inject_boot_config(unit: UnitConfig, boot_mount: Path) -> None:
    boot_mount.mkdir(parents=True, exist_ok=True)
    (boot_mount / "alleycattv.env").write_text(unit.env_file(), encoding="utf-8")
    (boot_mount / "alleycattv-hostname.txt").write_text(unit.hostname + "\n", encoding="utf-8")
    firstboot = unit.firstboot_script()
    script = boot_mount / "alleycattv-firstboot.sh"
    script.write_text(firstboot, encoding="utf-8")
    wpa = unit.wpa_supplicant()
    if wpa:
        # Pi OS Bookworm uses NetworkManager; still drop wpa for older images
        (boot_mount / "wpa_supplicant.conf").write_text(wpa, encoding="utf-8")
    print(f"Injected config for {unit.pi_id} into {boot_mount}")


def _find_boot_mount_hint() -> Path | None:
    """Try common Windows/Linux boot mount points after imaging."""
    candidates = []
    if platform.system() == "Windows":
        for letter in "EFGHIJKLMNOPQRSTUVWXYZ":
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
    return candidates[0] if candidates else None


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
    wifi_ssid = _prompt("Wi-Fi SSID (blank=skip)", defaults.wifi_ssid)
    wifi_psk = ""
    if wifi_ssid:
        wifi_psk = _prompt("Wi-Fi PSK", defaults.wifi_psk)

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
    )
    defaults.wifi_ssid = wifi_ssid
    defaults.wifi_psk = wifi_psk

    if dry_run:
        print("--- dry-run env ---")
        print(unit.env_file())
        if not inject_only:
            drive = _choose_drive()
            if drive and image:
                print(f"Would write {image} → {drive.device_id}")
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
        print("Waiting for boot partition to remount...")
        time.sleep(3)

    boot = _find_boot_mount_hint()
    if boot is None:
        raw = _prompt("Boot partition mount path (e.g. E:\\ or /media/pi/bootfs)")
        boot = Path(raw) if raw else None
    if boot is None or not boot.exists():
        # Still write artifacts to a staging folder for manual copy
        staging = Path(tempfile.mkdtemp(prefix="alleycattv-flash-"))
        _inject_boot_config(unit, staging)
        print(f"Could not find boot mount — files staged at {staging}")
        print("Copy alleycattv.env onto the SD boot partition, then eject.")
    else:
        _inject_boot_config(unit, boot)

    defaults.flashed.append(pi_id)
    print(f"Done: {pi_id}. Safely eject the SD card, insert the next, press Enter.")
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

    print("AlleycatTV distro — venue defaults (reused for each card)")
    defaults = SessionDefaults(
        server_url=_prompt("Content server URL", os.getenv("ALLEYCATV_SERVER", "")),
        mqtt_host=_prompt(
            "MQTT broker (HAOS Mosquitto)",
            os.getenv("ALLEYCATV_MQTT", "homeassistant.local"),
        ),
        mqtt_port=_prompt_int("MQTT port", 1883),
        mqtt_user=_prompt("MQTT username", ""),
        mqtt_pass=_prompt("MQTT password", ""),
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
