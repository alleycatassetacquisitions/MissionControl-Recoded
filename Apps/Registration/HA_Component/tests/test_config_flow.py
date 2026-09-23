"""Tests for the Registration config flow.

Groups:
  1. Happy path   — user enters a token → entry created
  2. Validation   — empty token rejected
  3. Guard        — second setup attempt aborts
"""
from __future__ import annotations

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.registration.const import CONF_MCS_TOKEN, DOMAIN


@pytest.mark.asyncio
async def test_config_flow_creates_entry(hass: HomeAssistant):
    """Happy path: user provides a token → entry created."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"

    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={CONF_MCS_TOKEN: "my-secret-token"},
    )
    assert result2["type"] == FlowResultType.CREATE_ENTRY
    assert result2["title"] == "Registration"
    assert result2["data"][CONF_MCS_TOKEN] == "my-secret-token"


@pytest.mark.asyncio
async def test_config_flow_trims_token_whitespace(hass: HomeAssistant):
    """Leading/trailing whitespace is stripped from the token."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={CONF_MCS_TOKEN: "  my-token  "},
    )
    assert result2["type"] == FlowResultType.CREATE_ENTRY
    assert result2["data"][CONF_MCS_TOKEN] == "my-token"


@pytest.mark.asyncio
async def test_config_flow_empty_token_shows_error(hass: HomeAssistant):
    """Empty token is rejected with a field error."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={CONF_MCS_TOKEN: ""},
    )
    assert result2["type"] == FlowResultType.FORM
    assert "mcs_token" in result2["errors"]


@pytest.mark.asyncio
async def test_config_flow_single_instance_guard(hass: HomeAssistant):
    """Second setup attempt aborts — Registration is single-instance."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_MCS_TOKEN: "existing-token"},
        unique_id=DOMAIN,
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "single_instance_allowed"
