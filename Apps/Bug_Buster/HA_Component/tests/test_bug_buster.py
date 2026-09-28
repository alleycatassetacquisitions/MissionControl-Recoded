"""Tests for Bug Buster — Proxmox client, MQTT spy, health, websocket gates."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.bug_buster.const import DOMAIN
from custom_components.bug_buster.mqtt_spy import preview_payload
from custom_components.bug_buster.proxmox import (
    ProxmoxClient,
    normalize_proxmox_url,
    error_kind,
)


class TestProxmoxHelpers:
    def test_normalize_adds_https_and_port(self):
        assert normalize_proxmox_url("192.168.1.1") == "https://192.168.1.1:8006"

    def test_normalize_preserves_full_url(self):
        assert normalize_proxmox_url("https://pve.local:8006") == "https://pve.local:8006"

    def test_error_kind_auth(self):
        assert error_kind("HTTP 401") == "auth"
        assert error_kind("API token missing") == "auth"

    def test_error_kind_connect(self):
        assert error_kind("Connection timeout") == "connect"

    def test_token_ready_requires_bang(self):
        client = ProxmoxClient(
            MagicMock(), "https://192.168.1.1:8006", "hass", "secret", verify_ssl=False
        )
        assert client.token_ready is False
        client.set_token("hass@pve!mc", "uuid-secret")
        assert client.token_ready is True

    def test_snapshot_from_resource(self):
        client = ProxmoxClient(
            MagicMock(),
            "https://192.168.1.1:8006",
            "hass@pve!mc",
            "uuid",
            default_node="pve",
        )
        snap = client.snapshot_from_resource(
            {"vmid": 101, "type": "lxc", "name": "mcs", "status": "running", "node": "pve"}
        )
        assert snap["vmid"] == 101
        assert snap["kind"] == "lxc"
        assert snap["online"] is True
        assert "cpu_percent" not in snap


class TestMqttPreview:
    def test_json_payload(self):
        raw = b'{"a": 1}'
        preview = preview_payload(raw)
        assert preview["kind"] == "json"
        assert '"a"' in preview["text"]

    def test_binary_payload(self):
        preview = preview_payload(bytes(range(32)))
        assert preview["kind"] == "binary"


@pytest.mark.asyncio
async def test_health_probe_uses_async_request(hass: HomeAssistant):
    from custom_components.bug_buster import health as health_mod

    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.release = MagicMock()

    with (
        patch.object(health_mod, "get_url", side_effect=lambda h, k: f"http://{k}.local"),
        patch.object(health_mod, "get_extra", return_value="tok"),
        patch.object(health_mod, "async_request", new_callable=AsyncMock, return_value=mock_resp) as req,
    ):
        rows = await health_mod.probe_companions(hass)

    assert len(rows) == 3
    assert all(r["ok"] for r in rows)
    assert req.await_count == 3


@pytest.mark.asyncio
async def test_health_not_configured(hass: HomeAssistant):
    from custom_components.bug_buster import health as health_mod

    with (
        patch.object(health_mod, "get_url", return_value=""),
        patch.object(health_mod, "get_extra", return_value=""),
        patch.object(health_mod, "async_request", new_callable=AsyncMock) as req,
    ):
        rows = await health_mod.probe_companions(hass)

    assert all(r["error"] == "not configured" for r in rows)
    req.assert_not_awaited()


@pytest.mark.asyncio
async def test_list_hosts_requires_admin(hass: HomeAssistant):
    from custom_components.bug_buster import __init__ as bb

    connection = MagicMock()
    connection.user = MagicMock(is_admin=False)
    connection.send_error = MagicMock()
    msg = {"id": 1, "type": f"{DOMAIN}/list_hosts"}

    await bb.ws_list_hosts(hass, connection, msg)
    connection.send_error.assert_called_once()
    assert connection.send_error.call_args[0][1] == "unauthorized"


@pytest.mark.asyncio
async def test_setup_entry_registers_client(hass: HomeAssistant):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"verify_ssl": False, "mqtt_topic": "mc/#"},
        title="Bug Buster",
    )
    entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.bug_buster._cc_proxmox",
            return_value=("https://192.168.1.1:8006", "pve", "hass@pve!mc", "uuid"),
        ),
        patch("custom_components.bug_buster.MqttSpy.start", new_callable=AsyncMock),
        patch(
            "custom_components.bug_buster.ProxmoxClient.list_guests",
            new_callable=AsyncMock,
            return_value=(
                [{"vmid": 100, "type": "lxc", "name": "mcs", "status": "running", "node": "pve"}],
                {"lxc": 1},
            ),
        ),
        patch(
            "custom_components.bug_buster.probe_companions",
            new_callable=AsyncMock,
            return_value=[],
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    data = hass.data[DOMAIN]
    assert data["client"] is not None
    assert 100 in data["hosts"]
    assert data["hosts"][100]["name"] == "mcs"
