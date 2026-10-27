"""Venue peer fan-out — MCS pushes runtime config to LXC companions.

Soft-fails per target; never raises into the HA /config caller.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

_LOGGER = logging.getLogger(__name__)


async def fanout_peers(
    *,
    api_token: str,
    peers: dict[str, str],
) -> dict[str, Any]:
    """POST /config to GBN and Net Time. Returns per-target status dict."""
    results: dict[str, Any] = {}
    mcs_url = (peers.get("mcs_url") or "").rstrip("/")
    gbn_url = (peers.get("gbn_url") or "").rstrip("/")
    net_time_url = (peers.get("net_time_url") or "").rstrip("/")
    net_time_token = (peers.get("net_time_token") or "").strip()
    host_clock_url = (peers.get("host_clock_url") or "").rstrip("/")

    if gbn_url and api_token:
        body = {
            "mcs_base": mcs_url,
            "mcs_token": api_token,
            "public_base": gbn_url,
        }
        results["gbn"] = await _post_config(gbn_url, api_token, body)
    elif gbn_url:
        results["gbn"] = {"ok": False, "error": "MCS token empty — skip GBN"}
    else:
        results["gbn"] = {"ok": False, "skipped": True, "reason": "gbn_url unset"}

    if net_time_url and net_time_token:
        body = {"host_clock_url": host_clock_url}
        results["net_time"] = await _post_config(net_time_url, net_time_token, body)
    elif net_time_url:
        results["net_time"] = {
            "ok": False,
            "error": "net_time_token empty — skip Net Time",
        }
    else:
        results["net_time"] = {
            "ok": False,
            "skipped": True,
            "reason": "net_time_url unset",
        }

    return results


async def _post_config(
    base_url: str,
    bearer: str,
    body: dict[str, Any],
) -> dict[str, Any]:
    url = f"{base_url.rstrip('/')}/config"
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.post(
                url,
                headers={"Authorization": f"Bearer {bearer}"},
                json=body,
            )
        ok = 200 <= resp.status_code < 300
        if not ok:
            _LOGGER.warning(
                "Peer fan-out %s -> HTTP %s: %s",
                url,
                resp.status_code,
                (resp.text or "")[:200],
            )
        else:
            _LOGGER.info("Peer fan-out OK %s -> %s", url, resp.status_code)
        return {"ok": ok, "status": resp.status_code}
    except Exception as exc:  # noqa: BLE001
        _LOGGER.warning("Peer fan-out failed %s: %s", url, exc)
        return {"ok": False, "error": str(exc)}
