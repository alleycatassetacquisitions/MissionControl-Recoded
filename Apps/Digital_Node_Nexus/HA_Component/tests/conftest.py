"""Pytest configuration for Digital Node Nexus HA integration tests.

Run from Apps/Digital_Node_Nexus/HA_Component/:

    cd Apps/Digital_Node_Nexus/HA_Component
    pytest
"""
import sys
from pathlib import Path

_ha_component_dir = Path(__file__).parent.parent
if str(_ha_component_dir) not in sys.path:
    sys.path.insert(0, str(_ha_component_dir))

_repo_root = _ha_component_dir.parent.parent.parent
for extra in [
    _repo_root / "Apps" / "Core_Configurator" / "HA_Component",
    _repo_root / "Libraries" / "Shared_HA_Helpers" / "HA_Component",
]:
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

import pytest

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture(autouse=True)
async def stub_external_integrations(hass, auto_enable_custom_integrations):
    """Stub dependency domains so HA can load digital_node_nexus."""
    from homeassistant import loader as ha_loader
    from pytest_homeassistant_custom_component.common import MockModule, mock_integration

    await ha_loader.async_get_custom_components(hass)
    mock_integration(hass, MockModule("core_configurator"), built_in=False)
    mock_integration(hass, MockModule("shared_libraries"), built_in=False)
    mock_integration(hass, MockModule("mqtt"), built_in=False)
    yield
