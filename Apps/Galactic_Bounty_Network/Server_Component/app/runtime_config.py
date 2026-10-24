"""Mutable MCS/public peer config for GBN.

Env (/etc/gbn.env) seeds values at process start. POST /config updates
runtime getters and persists last-good values (data dir + best-effort /etc).
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from app.config import DATA_DIR

_LOGGER = logging.getLogger(__name__)

_RUNTIME_ENV = DATA_DIR / "runtime_peers.env"
_ETC_ENV = Path("/etc/gbn.env")

_state: dict[str, str] = {
    "mcs_base": os.getenv("GBN_MCS_BASE", "").rstrip("/"),
    "mcs_token": os.getenv("GBN_MCS_TOKEN", "").strip(),
    "public_base": os.getenv("GBN_PUBLIC_BASE", "").rstrip("/"),
}


def load_persisted() -> None:
    """Overlay DATA_DIR/runtime_peers.env on top of process env (startup)."""
    if not _RUNTIME_ENV.is_file():
        return
    try:
        for line in _RUNTIME_ENV.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()
            if key == "GBN_MCS_BASE" and value:
                _state["mcs_base"] = value.rstrip("/")
            elif key == "GBN_MCS_TOKEN" and value:
                _state["mcs_token"] = value
            elif key == "GBN_PUBLIC_BASE" and value:
                _state["public_base"] = value.rstrip("/")
        _LOGGER.info("GBN loaded runtime peers from %s", _RUNTIME_ENV)
    except Exception as exc:  # noqa: BLE001
        _LOGGER.warning("GBN failed to load %s: %s", _RUNTIME_ENV, exc)


def mcs_base() -> str:
    return _state["mcs_base"]


def mcs_token() -> str:
    return _state["mcs_token"]


def public_base() -> str:
    return _state["public_base"]


def apply_config(
    *,
    mcs_base: str = "",
    mcs_token: str = "",
    public_base: str = "",
) -> dict[str, Any]:
    """Apply non-empty fields; persist; return applied snapshot."""
    if mcs_base:
        _state["mcs_base"] = mcs_base.strip().rstrip("/")
    if mcs_token:
        _state["mcs_token"] = mcs_token.strip()
    if public_base:
        _state["public_base"] = public_base.strip().rstrip("/")
    _persist()
    return {
        "mcs_base": _state["mcs_base"],
        "mcs_token_set": bool(_state["mcs_token"]),
        "public_base": _state["public_base"],
    }


def auth_token_matches(bearer: str | None) -> bool:
    """Venue token = current MCS Bearer (same value MCS uses to fan-out)."""
    expected = _state["mcs_token"]
    if not expected or not bearer:
        return False
    return bearer == expected


def _persist() -> None:
    lines = [
        f"GBN_MCS_BASE={_state['mcs_base']}",
        f"GBN_MCS_TOKEN={_state['mcs_token']}",
        f"GBN_PUBLIC_BASE={_state['public_base']}",
    ]
    body = "\n".join(lines) + "\n"
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        _RUNTIME_ENV.write_text(body, encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        _LOGGER.warning("GBN could not persist %s: %s", _RUNTIME_ENV, exc)
    _merge_etc_env(
        {
            "GBN_MCS_BASE": _state["mcs_base"],
            "GBN_MCS_TOKEN": _state["mcs_token"],
            "GBN_PUBLIC_BASE": _state["public_base"],
        }
    )


def _merge_etc_env(updates: dict[str, str]) -> None:
    """Best-effort merge into /etc/gbn.env (may be root-owned)."""
    try:
        existing: dict[str, str] = {}
        order: list[str] = []
        if _ETC_ENV.is_file():
            for line in _ETC_ENV.read_text(encoding="utf-8").splitlines():
                if not line.strip() or line.strip().startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                if key not in existing:
                    order.append(key)
                existing[key] = value
        for key, value in updates.items():
            if key not in existing:
                order.append(key)
            existing[key] = value
        text = "".join(f"{k}={existing[k]}\n" for k in order)
        _ETC_ENV.write_text(text, encoding="utf-8")
        _LOGGER.info("GBN updated %s", _ETC_ENV)
    except Exception as exc:  # noqa: BLE001
        _LOGGER.debug("GBN /etc/gbn.env persist skipped: %s", exc)
