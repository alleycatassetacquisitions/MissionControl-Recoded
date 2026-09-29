"""MQTT command topic segment resolution for AlleycatTV publishes.

TV topics use an explicit ``device`` segment (unlike DNN):
  mc/tv/cmd/device/{PI_ID}/…
  mc/tv/cmd/all/…
  mc/tv/cmd/broadcast/{id}/…
"""
from __future__ import annotations


def resolve_cmd_segments(
    *,
    pi_id: str | None = None,
    target: str | None = None,
    broadcast_group_id: str | None = None,
) -> list[str]:
    """Build ``cmd/...`` segments under ``mc/tv/``."""
    if pi_id:
        return ["cmd", "device", pi_id]
    if broadcast_group_id:
        return ["cmd", "broadcast", broadcast_group_id]
    if target == "all":
        return ["cmd", "all"]
    raise ValueError(
        "AlleycatTV command requires pi_id, target=all, or broadcast_group_id"
    )
