"""MQTT command topic segment resolution for DNN publishes."""
from __future__ import annotations


def resolve_cmd_segments(
    *,
    device_id: str | None = None,
    target: str | None = None,
    broadcast_group_id: str | None = None,
    default_all_for_stamps: bool = False,
) -> list[str]:
    """Build ``cmd/...`` segments under ``mc/dnn/``.

    Priority: explicit device_id → broadcast_group_id → target=all →
    (optional) all when only player/filter stamps are present.
    """
    if device_id:
        return ["cmd", device_id]
    if broadcast_group_id:
        return ["cmd", "broadcast", broadcast_group_id]
    if target == "all":
        return ["cmd", "all"]
    if default_all_for_stamps:
        return ["cmd", "all"]
    raise ValueError(
        "page/LED/haptic requires device_id, target=all, or broadcast_group_id "
        "(or player_id/role/neocorp for page)"
    )
