"""Tests for the Core Configurator integration.

Groups:
  1. urlutil        — pure-unit, no hass needed
  2. helpers        — get_url / get_extra / apply_service against mocked hass.data
  3. Config flow    — user step, single-instance guard, YAML import
  4. async_setup_entry — hass.data populated, event fired
  5. Websocket      — get_services, get_url, set_service (admin / non-admin)

Design contract under test:
  - get_url is fail-closed: returns "" when no URL is stored (never falls back to
    a hardcoded IP).
  - set_service requires an admin user.
  - core_configurator_updated fires on every successful write.
  - Config entry is single-instance (second setup attempt aborts).
  - apply_service writes one service from another integration; no-op if CC absent.
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.core_configurator.const import (
    DOMAIN,
    EVENT_UPDATED,
    KEY_MASTER_CONTROL_SERVER,
    KEY_CENTRAL_PRIMARY,
    KEY_CENTRAL_SECONDARY,
    KEY_ALLEYCATTV,
    KEY_GBN,
    KEY_PROXMOX,
    SERVICE_CATALOG,
)
from custom_components.core_configurator.urlutil import (
    empty_services,
    normalize_url,
    services_from_mapping,
)
from custom_components.core_configurator.helpers import (
    get_extra,
    get_url,
    apply_service,
)


# ---------------------------------------------------------------------------
# 1. urlutil — pure unit tests
# ---------------------------------------------------------------------------


class TestNormalizeUrl:
    def test_blank_returns_empty(self):
        assert normalize_url("") == ""

    def test_whitespace_only_returns_empty(self):
        assert normalize_url("   ") == ""

    def test_none_like_returns_empty(self):
        # None is coerced to "" via (raw or "")
        assert normalize_url(None) == ""  # type: ignore[arg-type]

    def test_adds_http_for_plain_host(self):
        assert normalize_url("192.168.1.10") == "http://192.168.1.10"

    def test_adds_http_with_port(self):
        assert normalize_url("192.168.1.10:8090") == "http://192.168.1.10:8090"

    def test_preserves_existing_http_scheme(self):
        assert normalize_url("http://192.168.1.10:8090") == "http://192.168.1.10:8090"

    def test_preserves_existing_https_scheme(self):
        assert normalize_url("https://example.com") == "https://example.com"

    def test_strips_trailing_slash(self):
        assert normalize_url("http://192.168.1.10/") == "http://192.168.1.10"

    def test_proxmox_plain_host_gets_https_and_port(self):
        result = normalize_url("192.168.1.1", key=KEY_PROXMOX)
        assert result == "https://192.168.1.1:8006"

    def test_proxmox_host_colon_port_gets_https(self):
        # Already has a port in the hostname segment — still gets https://
        result = normalize_url("192.168.1.1:8006", key=KEY_PROXMOX)
        assert result == "https://192.168.1.1:8006"

    def test_proxmox_full_url_with_port_unchanged(self):
        result = normalize_url("https://192.168.1.1:8006", key=KEY_PROXMOX)
        assert result == "https://192.168.1.1:8006"

    def test_proxmox_url_missing_port_adds_port(self):
        result = normalize_url("https://192.168.1.1", key=KEY_PROXMOX)
        assert result == "https://192.168.1.1:8006"


class TestEmptyServices:
    def test_returns_all_catalog_keys(self):
        services = empty_services()
        catalog_keys = {s["key"] for s in SERVICE_CATALOG}
        assert set(services.keys()) == catalog_keys

    def test_all_urls_are_empty_strings(self):
        """Fail-closed contract: no hardcoded IPs."""
        services = empty_services()
        for key, val in services.items():
            assert val["url"] == "", f"Key {key!r} has a non-empty default URL"

    def test_proxmox_extra_has_default_node(self):
        services = empty_services()
        assert services[KEY_PROXMOX]["extra"]["node"] == "pve"

    def test_non_proxmox_extra_is_empty_dict(self):
        services = empty_services()
        for key, val in services.items():
            if key != KEY_PROXMOX:
                assert val["extra"] == {}, f"Key {key!r} should have empty extra"


class TestServicesFromMapping:
    def test_empty_mapping_produces_empty_urls(self):
        services = services_from_mapping({})
        for key, val in services.items():
            assert val["url"] == ""

    def test_single_key_populated(self):
        services = services_from_mapping({KEY_ALLEYCATTV: "http://tv.local"})
        assert services[KEY_ALLEYCATTV]["url"] == "http://tv.local"
        # Others remain empty
        assert services[KEY_GBN]["url"] == ""
        assert services[KEY_PROXMOX]["url"] == ""

    def test_proxmox_node_override(self):
        services = services_from_mapping({"proxmox_node": "mynode"})
        assert services[KEY_PROXMOX]["extra"]["node"] == "mynode"

    def test_proxmox_node_none_leaves_default(self):
        # proxmox_node is present but None → data.get("proxmox_node") is None
        # → the `is not None` guard is False → block is skipped entirely
        # → empty_services() default "pve" is untouched.
        services = services_from_mapping({"proxmox_node": None})
        assert services[KEY_PROXMOX]["extra"]["node"] == "pve"

    def test_url_normalized_on_import(self):
        services = services_from_mapping({KEY_GBN: "192.168.1.206:8100"})
        assert services[KEY_GBN]["url"] == "http://192.168.1.206:8100"

    def test_all_yaml_keys_populated(self):
        data = {
            KEY_MASTER_CONTROL_SERVER: "http://192.168.1.10:8700",
            KEY_CENTRAL_PRIMARY: "https://cloud.example.com",
            KEY_CENTRAL_SECONDARY: "http://192.168.1.234:8090",
            KEY_ALLEYCATTV: "http://tv.local",
            KEY_GBN: "http://192.168.1.206:8100",
            KEY_PROXMOX: "192.168.1.1",
            "proxmox_node": "pve",
        }
        services = services_from_mapping(data)
        assert services[KEY_MASTER_CONTROL_SERVER]["url"] == "http://192.168.1.10:8700"
        assert services[KEY_CENTRAL_PRIMARY]["url"] == "https://cloud.example.com"
        assert services[KEY_CENTRAL_SECONDARY]["url"] == "http://192.168.1.234:8090"
        assert services[KEY_ALLEYCATTV]["url"] == "http://tv.local"
        assert services[KEY_GBN]["url"] == "http://192.168.1.206:8100"
        assert services[KEY_PROXMOX]["url"] == "https://192.168.1.1:8006"
        assert services[KEY_PROXMOX]["extra"]["node"] == "pve"

    def test_mcs_token_from_yaml(self):
        from custom_components.core_configurator.const import YAML_MCS_TOKEN

        services = services_from_mapping(
            {
                KEY_MASTER_CONTROL_SERVER: "http://192.168.1.10:8700",
                YAML_MCS_TOKEN: "  secret-token  ",
            }
        )
        assert services[KEY_MASTER_CONTROL_SERVER]["extra"]["token"] == "secret-token"

    def test_mcs_token_blank_clears_extra(self):
        from custom_components.core_configurator.const import YAML_MCS_TOKEN

        services = services_from_mapping({YAML_MCS_TOKEN: "   "})
        assert services[KEY_MASTER_CONTROL_SERVER]["extra"]["token"] == ""


# ---------------------------------------------------------------------------
# 2. helpers — get_url / get_extra / apply_service
# ---------------------------------------------------------------------------


class TestGetUrl:
    def test_returns_empty_when_domain_absent(self, hass: HomeAssistant):
        """Fail-closed: no URL configured → empty string, never a hardcoded IP."""
        assert get_url(hass, KEY_ALLEYCATTV) == ""

    def test_returns_empty_when_services_key_missing(self, hass: HomeAssistant):
        hass.data[DOMAIN] = {"services": {}, "entry_id": None}
        assert get_url(hass, KEY_ALLEYCATTV) == ""

    def test_returns_stored_url(self, hass: HomeAssistant):
        hass.data[DOMAIN] = {
            "services": {KEY_ALLEYCATTV: {"url": "http://tv.local", "extra": {}}},
            "entry_id": None,
        }
        assert get_url(hass, KEY_ALLEYCATTV) == "http://tv.local"

    def test_strips_trailing_slash_from_stored_url(self, hass: HomeAssistant):
        hass.data[DOMAIN] = {
            "services": {KEY_ALLEYCATTV: {"url": "http://tv.local/", "extra": {}}},
            "entry_id": None,
        }
        assert get_url(hass, KEY_ALLEYCATTV) == "http://tv.local"

    def test_custom_default_returned_when_no_url(self, hass: HomeAssistant):
        hass.data[DOMAIN] = {"services": {}, "entry_id": None}
        assert get_url(hass, KEY_ALLEYCATTV, default="http://fallback") == "http://fallback"

    def test_stored_url_takes_priority_over_default(self, hass: HomeAssistant):
        hass.data[DOMAIN] = {
            "services": {KEY_ALLEYCATTV: {"url": "http://real.local", "extra": {}}},
            "entry_id": None,
        }
        assert get_url(hass, KEY_ALLEYCATTV, default="http://fallback") == "http://real.local"

    def test_mcs_url_stored_and_retrieved(self, hass: HomeAssistant):
        """master_control_server key works like any other service key."""
        hass.data[DOMAIN] = {
            "services": {
                KEY_MASTER_CONTROL_SERVER: {"url": "http://192.168.1.10:8700", "extra": {}},
            },
            "entry_id": None,
        }
        assert get_url(hass, KEY_MASTER_CONTROL_SERVER) == "http://192.168.1.10:8700"

    def test_central_primary_stored_and_retrieved(self, hass: HomeAssistant):
        hass.data[DOMAIN] = {
            "services": {
                KEY_CENTRAL_PRIMARY: {"url": "https://cloud.example.com", "extra": {}},
            },
            "entry_id": None,
        }
        assert get_url(hass, KEY_CENTRAL_PRIMARY) == "https://cloud.example.com"

    def test_central_secondary_stored_and_retrieved(self, hass: HomeAssistant):
        hass.data[DOMAIN] = {
            "services": {
                KEY_CENTRAL_SECONDARY: {"url": "http://192.168.1.234:8090", "extra": {}},
            },
            "entry_id": None,
        }
        assert get_url(hass, KEY_CENTRAL_SECONDARY) == "http://192.168.1.234:8090"


class TestGetExtra:
    def test_returns_default_when_domain_absent(self, hass: HomeAssistant):
        assert get_extra(hass, KEY_PROXMOX, "node", default="pve") == "pve"

    def test_returns_default_when_field_absent(self, hass: HomeAssistant):
        hass.data[DOMAIN] = {
            "services": {KEY_PROXMOX: {"url": "", "extra": {}}},
            "entry_id": None,
        }
        assert get_extra(hass, KEY_PROXMOX, "node", default="pve") == "pve"

    def test_returns_stored_value(self, hass: HomeAssistant):
        hass.data[DOMAIN] = {
            "services": {KEY_PROXMOX: {"url": "", "extra": {"node": "mynode"}}},
            "entry_id": None,
        }
        assert get_extra(hass, KEY_PROXMOX, "node", default="pve") == "mynode"

    def test_returns_default_for_empty_string_value(self, hass: HomeAssistant):
        hass.data[DOMAIN] = {
            "services": {KEY_PROXMOX: {"url": "", "extra": {"node": ""}}},
            "entry_id": None,
        }
        assert get_extra(hass, KEY_PROXMOX, "node", default="pve") == "pve"


class TestApplyService:
    """apply_service — called by other integrations to write a URL into CC."""

    def _setup_cc(self, hass: HomeAssistant):
        """Put a minimal CC data structure into hass.data."""
        hass.data[DOMAIN] = {
            "services": empty_services(),
            "entry_id": None,
        }

    def test_returns_false_when_cc_not_loaded(self, hass: HomeAssistant):
        """No-op when Core Configurator has not been set up yet."""
        result = apply_service(hass, KEY_GBN, url="http://192.168.1.206:8100")
        assert result is False

    def test_returns_true_when_cc_loaded(self, hass: HomeAssistant):
        self._setup_cc(hass)
        result = apply_service(hass, KEY_GBN, url="http://192.168.1.206:8100")
        assert result is True

    def test_writes_url_into_services(self, hass: HomeAssistant):
        self._setup_cc(hass)
        apply_service(hass, KEY_GBN, url="http://192.168.1.206:8100")
        assert get_url(hass, KEY_GBN) == "http://192.168.1.206:8100"

    def test_url_is_normalized(self, hass: HomeAssistant):
        """apply_service passes the URL through normalize_url."""
        self._setup_cc(hass)
        apply_service(hass, KEY_GBN, url="192.168.1.206:8100")
        assert get_url(hass, KEY_GBN) == "http://192.168.1.206:8100"

    def test_extra_fields_merged(self, hass: HomeAssistant):
        self._setup_cc(hass)
        apply_service(hass, KEY_PROXMOX, extra={"node": "pve2"})
        assert get_extra(hass, KEY_PROXMOX, "node") == "pve2"

    def test_extra_merged_not_replaced(self, hass: HomeAssistant):
        """Existing extra fields not in the update dict are preserved."""
        self._setup_cc(hass)
        hass.data[DOMAIN]["services"][KEY_PROXMOX]["extra"] = {"node": "pve", "other": "val"}
        apply_service(hass, KEY_PROXMOX, extra={"node": "pve2"})
        # "other" should still be there
        stored = hass.data[DOMAIN]["services"][KEY_PROXMOX]["extra"]
        assert stored["other"] == "val"
        assert stored["node"] == "pve2"

    def test_mcs_url_written(self, hass: HomeAssistant):
        """apply_service works for the master_control_server key."""
        self._setup_cc(hass)
        apply_service(hass, KEY_MASTER_CONTROL_SERVER, url="http://192.168.1.10:8700")
        assert get_url(hass, KEY_MASTER_CONTROL_SERVER) == "http://192.168.1.10:8700"

    def test_central_primary_written(self, hass: HomeAssistant):
        self._setup_cc(hass)
        apply_service(hass, KEY_CENTRAL_PRIMARY, url="https://cloud.example.com")
        assert get_url(hass, KEY_CENTRAL_PRIMARY) == "https://cloud.example.com"

    def test_fires_updated_event(self, hass: HomeAssistant):
        """apply_service fires core_configurator_updated after writing."""
        self._setup_cc(hass)
        events: list = []
        hass.bus.async_listen(EVENT_UPDATED, lambda e: events.append(e))
        apply_service(hass, KEY_GBN, url="http://192.168.1.206:8100")
        assert len(events) == 1
        assert events[0].data["key"] == KEY_GBN


# ---------------------------------------------------------------------------
# 3. Config flow
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_config_flow_user_step_creates_entry(hass: HomeAssistant):
    """User fills in the form → config entry created with services dict."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"

    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={KEY_ALLEYCATTV: "http://tv.local", KEY_GBN: "http://192.168.1.206:8100"},
    )
    assert result2["type"] == FlowResultType.CREATE_ENTRY
    assert result2["title"] == "Core Configurator"
    services = result2["data"]["services"]
    assert services[KEY_ALLEYCATTV]["url"] == "http://tv.local"
    assert services[KEY_GBN]["url"] == "http://192.168.1.206:8100"


@pytest.mark.asyncio
async def test_config_flow_single_instance_guard(hass: HomeAssistant):
    """Second setup attempt aborts — only one Core Configurator entry allowed."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"services": empty_services()},
        unique_id=DOMAIN,
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "single_instance_allowed"


@pytest.mark.asyncio
async def test_config_flow_yaml_import_creates_entry(hass: HomeAssistant):
    """async_step_import accepts YAML seed and creates the config entry."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "import"},
        data={KEY_ALLEYCATTV: "http://tv.local", "proxmox_node": "pve"},
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    services = result["data"]["services"]
    assert services[KEY_ALLEYCATTV]["url"] == "http://tv.local"
    assert services[KEY_PROXMOX]["extra"]["node"] == "pve"


@pytest.mark.asyncio
async def test_config_flow_yaml_import_aborts_if_entry_exists(hass: HomeAssistant):
    """YAML import aborts when an entry already exists (idempotent on reload)."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"services": empty_services()},
        unique_id=DOMAIN,
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "import"},
        data={},
    )
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "single_instance_allowed"


# ---------------------------------------------------------------------------
# 4. async_setup_entry
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_setup_entry_populates_hass_data(hass: HomeAssistant):
    """async_setup_entry loads services into hass.data[DOMAIN]."""
    services = services_from_mapping({KEY_GBN: "http://192.168.1.206:8100"})
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"services": services},
        unique_id=DOMAIN,
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    stored = hass.data[DOMAIN]["services"]
    assert stored[KEY_GBN]["url"] == "http://192.168.1.206:8100"
    # Other keys present but empty (fail-closed)
    assert stored[KEY_ALLEYCATTV]["url"] == ""


@pytest.mark.asyncio
async def test_setup_entry_fires_updated_event(hass: HomeAssistant):
    """core_configurator_updated is fired during setup so listeners can resync."""
    events: list = []
    hass.bus.async_listen(EVENT_UPDATED, lambda e: events.append(e))

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"services": empty_services()},
        unique_id=DOMAIN,
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert len(events) >= 1
    assert events[0].data["key"] is None  # full-catalog refresh on setup


@pytest.mark.asyncio
async def test_unload_entry_clears_hass_data(hass: HomeAssistant):
    """async_unload_entry removes the domain from hass.data."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"services": empty_services()},
        unique_id=DOMAIN,
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert DOMAIN in hass.data

    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    assert DOMAIN not in hass.data


# ---------------------------------------------------------------------------
# 5. Websocket commands
# ---------------------------------------------------------------------------


@pytest.fixture
async def configured_entry(hass: HomeAssistant):
    """Set up a loaded Core Configurator entry with one URL pre-configured."""
    services = services_from_mapping({KEY_ALLEYCATTV: "http://tv.local"})
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"services": services},
        unique_id=DOMAIN,
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


@pytest.mark.asyncio
async def test_ws_get_services_returns_catalog(hass: HomeAssistant, configured_entry, hass_ws_client):
    """get_services returns the full catalog including all service keys."""
    client = await hass_ws_client(hass)
    await client.send_json({"id": 1, "type": f"{DOMAIN}/get_services"})
    msg = await client.receive_json()

    assert msg["success"] is True
    keys = {s["key"] for s in msg["result"]["services"]}
    catalog_keys = {s["key"] for s in SERVICE_CATALOG}
    assert keys == catalog_keys


@pytest.mark.asyncio
async def test_ws_get_url_returns_stored_url(hass: HomeAssistant, configured_entry, hass_ws_client):
    """get_url returns the URL that was stored in the config entry."""
    client = await hass_ws_client(hass)
    await client.send_json(
        {"id": 2, "type": f"{DOMAIN}/get_url", "key": KEY_ALLEYCATTV}
    )
    msg = await client.receive_json()

    assert msg["success"] is True
    assert msg["result"]["url"] == "http://tv.local"
    assert msg["result"]["key"] == KEY_ALLEYCATTV


@pytest.mark.asyncio
async def test_ws_get_url_returns_empty_for_unconfigured_key(
    hass: HomeAssistant, configured_entry, hass_ws_client
):
    """get_url returns empty string for a key that has no stored URL (fail-closed)."""
    client = await hass_ws_client(hass)
    await client.send_json(
        {"id": 3, "type": f"{DOMAIN}/get_url", "key": KEY_GBN}
    )
    msg = await client.receive_json()

    assert msg["success"] is True
    assert msg["result"]["url"] == ""


@pytest.mark.asyncio
async def test_ws_set_service_non_admin_rejected(
    hass: HomeAssistant, configured_entry, hass_ws_client
):
    """set_service must reject non-admin users with an unauthorized error."""
    # hass_ws_client authenticates as a regular (non-admin) user when passed
    # a non-admin user object; here we rely on the default fixture user which
    # is admin, so we manually create a non-admin mock connection.
    #
    # Patch the connection's user to simulate a non-admin caller.
    client = await hass_ws_client(hass)

    with patch(
        "homeassistant.components.websocket_api.connection.ActiveConnection.user",
        new_callable=lambda: property(lambda self: MagicMock(is_admin=False)),
    ):
        await client.send_json(
            {
                "id": 4,
                "type": f"{DOMAIN}/set_service",
                "key": KEY_GBN,
                "url": "http://192.168.1.206:8100",
            }
        )
        msg = await client.receive_json()

    assert msg["success"] is False
    assert msg["error"]["code"] == "unauthorized"


@pytest.mark.asyncio
async def test_ws_set_service_admin_updates_url(
    hass: HomeAssistant, configured_entry, hass_ws_client
):
    """set_service updates the stored URL and fires core_configurator_updated."""
    events: list = []
    hass.bus.async_listen(EVENT_UPDATED, lambda e: events.append(e))

    client = await hass_ws_client(hass)
    await client.send_json(
        {
            "id": 5,
            "type": f"{DOMAIN}/set_service",
            "key": KEY_GBN,
            "url": "http://192.168.1.206:8100",
        }
    )
    msg = await client.receive_json()
    await hass.async_block_till_done()

    assert msg["success"] is True
    assert msg["result"]["ok"] is True
    assert msg["result"]["url"] == "http://192.168.1.206:8100"

    # Verify the change persisted in hass.data
    assert get_url(hass, KEY_GBN) == "http://192.168.1.206:8100"

    # Verify the event fired with the changed key
    assert any(e.data["key"] == KEY_GBN for e in events)


@pytest.mark.asyncio
async def test_ws_set_service_extra_field(
    hass: HomeAssistant, configured_entry, hass_ws_client
):
    """set_service can update extra fields (e.g. Proxmox node name)."""
    client = await hass_ws_client(hass)
    await client.send_json(
        {
            "id": 6,
            "type": f"{DOMAIN}/set_service",
            "key": KEY_PROXMOX,
            "url": "https://192.168.1.1:8006",
            "extra": {"node": "mynode"},
        }
    )
    msg = await client.receive_json()
    await hass.async_block_till_done()

    assert msg["success"] is True
    assert msg["result"]["extra"]["node"] == "mynode"
    assert get_extra(hass, KEY_PROXMOX, "node") == "mynode"
