"""Tests for the Registration config flow.

Groups:
  1. Happy path — install-only form creates an empty entry
  2. Guard      — second setup attempt aborts
"""
from __future__ import annotations

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.registration.const import DOMAIN


@pytest.mark.asyncio
async def test_config_flow_creates_entry(hass: HomeAssistant):
    """Happy path: confirm install → entry created with no credentials."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"

    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={},
    )
    assert result2["type"] == FlowResultType.CREATE_ENTRY
    assert result2["title"] == "Registration"
    assert result2["data"] == {}


@pytest.mark.asyncio
async def test_config_flow_single_instance_guard(hass: HomeAssistant):
    """Second setup attempt aborts — Registration is single-instance."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={},
        unique_id=DOMAIN,
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "single_instance_allowed"
