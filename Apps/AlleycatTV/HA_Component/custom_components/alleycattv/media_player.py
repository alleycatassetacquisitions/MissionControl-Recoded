"""Media player entities for AlleycatTV Pis (one per fabric device)."""
from __future__ import annotations

from homeassistant.components.media_player import (
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, SIGNAL_NEW_DEVICE, SIGNAL_UPDATE
from .device import device_data, device_info

_STATE_MAP = {
    "playing": MediaPlayerState.PLAYING,
    "paused": MediaPlayerState.PAUSED,
    "stopped": MediaPlayerState.IDLE,
    "idle": MediaPlayerState.IDLE,
    "interrupted": MediaPlayerState.PLAYING,
}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    known: set[str] = set()

    @callback
    def _add(pi_id: str) -> None:
        if pi_id in known:
            return
        known.add(pi_id)
        async_add_entities([AlleycatTVMediaPlayer(hass, pi_id)])

    entry.async_on_unload(
        async_dispatcher_connect(hass, SIGNAL_NEW_DEVICE, _add)
    )
    for pi_id in list(hass.data.get(DOMAIN, {}).get("devices", {})):
        _add(pi_id)


class AlleycatTVMediaPlayer(MediaPlayerEntity):
    _attr_has_entity_name = True
    _attr_name = "Broadcast"
    _attr_should_poll = False
    _attr_supported_features = (
        MediaPlayerEntityFeature.PLAY
        | MediaPlayerEntityFeature.STOP
        | MediaPlayerEntityFeature.VOLUME_SET
    )

    def __init__(self, hass: HomeAssistant, pi_id: str) -> None:
        self.hass = hass
        self._pi_id = pi_id
        self._attr_unique_id = f"{DOMAIN}_{pi_id}_player"
        self._unsub = None

    async def async_added_to_hass(self) -> None:
        self._unsub = async_dispatcher_connect(
            self.hass, SIGNAL_UPDATE, self._on_update
        )

    async def async_will_remove_from_hass(self) -> None:
        if self._unsub:
            self._unsub()

    @callback
    def _on_update(self, pi_id: str) -> None:
        if pi_id == self._pi_id:
            self.async_write_ha_state()

    @property
    def device_info(self):
        return device_info(self._pi_id)

    @property
    def available(self) -> bool:
        data = device_data(self.hass, self._pi_id)
        if "online" in data:
            return bool(data.get("online"))
        # Fall back to fabric presence entity when playback telemetry is absent.
        presence = self.hass.states.get(
            f"sensor.{DOMAIN}_{self._pi_id.replace('-', '_')}_presence"
        )
        return presence is not None and presence.state == "online"

    @property
    def state(self) -> MediaPlayerState:
        raw = (device_data(self.hass, self._pi_id).get("state") or "idle").lower()
        return _STATE_MAP.get(raw, MediaPlayerState.IDLE)

    @property
    def media_title(self) -> str | None:
        return device_data(self.hass, self._pi_id).get("current_file") or None

    @property
    def extra_state_attributes(self) -> dict:
        data = device_data(self.hass, self._pi_id)
        return {
            "broadcast_group_id": data.get("broadcast_group_id") or "",
            "pi_id": self._pi_id,
            "next_file": data.get("next_file"),
        }

    def _broadcast_group_id(self) -> str:
        return device_data(self.hass, self._pi_id).get("broadcast_group_id") or ""

    async def async_media_play(self) -> None:
        bg = self._broadcast_group_id()
        if bg:
            await self.hass.services.async_call(
                DOMAIN,
                "play_broadcast_group",
                {"broadcast_group_id": bg},
                blocking=True,
            )

    async def async_media_stop(self) -> None:
        bg = self._broadcast_group_id()
        if bg:
            await self.hass.services.async_call(
                DOMAIN,
                "stop_broadcast_group",
                {"broadcast_group_id": bg},
                blocking=True,
            )

    async def async_set_volume_level(self, volume: float) -> None:
        bg = self._broadcast_group_id()
        if bg:
            await self.hass.services.async_call(
                DOMAIN,
                "set_volume_broadcast_group",
                {"broadcast_group_id": bg, "volume": int(volume * 100)},
                blocking=True,
            )
