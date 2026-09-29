"""Drive discovery and safety guards for SD flashing (Windows + Linux)."""
from __future__ import annotations

import platform
import re
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class DriveInfo:
    device_id: str  # e.g. \\\\.\\PHYSICALDRIVE2 or /dev/sdb
    label: str
    size_bytes: int
    bus: str = ""

    @property
    def size_gb(self) -> float:
        return self.size_bytes / (1024**3) if self.size_bytes else 0.0


# Refuse anything that looks like a system / large fixed disk.
_MIN_REMOVABLE_HINT_GB = 4
_MAX_SD_HINT_GB = 256


def is_safe_flash_target(drive: DriveInfo, *, allow_large: bool = False) -> tuple[bool, str]:
    """Return (ok, reason). Never allow empty device id or tiny/huge surprises."""
    if not drive.device_id:
        return False, "empty device id"
    size_gb = drive.size_gb
    if size_gb < _MIN_REMOVABLE_HINT_GB:
        return False, f"drive too small ({size_gb:.1f} GiB) — likely not an SD card"
    if not allow_large and size_gb > _MAX_SD_HINT_GB:
        return False, f"drive too large ({size_gb:.1f} GiB) — refusing system disk"

    bus = (drive.bus or "").lower()
    label = (drive.label or "").lower()
    # Windows: NVMe / SCSI fixed disks often lack USB/SD bus tags
    if "nvme" in bus or "nvme" in label:
        return False, "looks like NVMe system storage"
    if platform.system() == "Windows":
        # PHYSICALDRIVE0 is almost always the boot disk
        if re.search(r"PHYSICALDRIVE0\b", drive.device_id, re.I):
            return False, "refusing PHYSICALDRIVE0 (usually the system disk)"
    else:
        if drive.device_id in ("/dev/sda", "/dev/nvme0n1"):
            return False, f"refusing likely system disk {drive.device_id}"
    return True, "ok"


def list_removable_drives() -> list[DriveInfo]:
    """Best-effort removable/USB drive list. May be empty without admin rights."""
    system = platform.system()
    if system == "Windows":
        return _list_windows()
    return _list_linux()


def _list_windows() -> list[DriveInfo]:
    # PowerShell CIM — MediaType 11 = Removable Media when available
    ps = (
        "Get-CimInstance Win32_DiskDrive | "
        "Select-Object DeviceID,Model,Size,InterfaceType,MediaType | "
        "ConvertTo-Csv -NoTypeInformation"
    )
    try:
        out = subprocess.check_output(
            ["powershell", "-NoProfile", "-Command", ps],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []

    drives: list[DriveInfo] = []
    lines = [ln.strip() for ln in out.splitlines() if ln.strip()]
    if len(lines) < 2:
        return []
    # header: "DeviceID","Model","Size","InterfaceType","MediaType"
    for row in lines[1:]:
        parts = [p.strip().strip('"') for p in row.split(",")]
        if len(parts) < 5:
            continue
        device_id, model, size_s, iface, media = parts[:5]
        try:
            size = int(float(size_s)) if size_s else 0
        except ValueError:
            size = 0
        media_l = media.lower()
        iface_l = iface.lower()
        # Prefer removable / USB / SD; still list others so operator can choose carefully
        hint = media_l + " " + iface_l
        if "fixed" in media_l and "usb" not in iface_l and "sd" not in hint:
            # Skip obvious fixed SATA unless USB
            if iface_l in ("ide", "scsi", "nvme"):
                continue
        drives.append(
            DriveInfo(
                device_id=device_id,
                label=model or device_id,
                size_bytes=size,
                bus=iface,
            )
        )
    return drives


def _list_linux() -> list[DriveInfo]:
    try:
        out = subprocess.check_output(
            ["lsblk", "-b", "-d", "-n", "-o", "NAME,SIZE,TRAN,TYPE,MODEL"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []
    drives: list[DriveInfo] = []
    for line in out.splitlines():
        parts = line.split(None, 4)
        if len(parts) < 4:
            continue
        name, size_s, tran, typ = parts[0], parts[1], parts[2], parts[3]
        model = parts[4] if len(parts) > 4 else name
        if typ != "disk":
            continue
        if tran not in ("usb", "mmc", "sd"):
            continue
        try:
            size = int(size_s)
        except ValueError:
            size = 0
        drives.append(
            DriveInfo(
                device_id=f"/dev/{name}",
                label=model.strip() or name,
                size_bytes=size,
                bus=tran,
            )
        )
    return drives
