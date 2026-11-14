"""Pytest configuration for Game Master HA integration tests.

Run pytest from Apps/Game_Master/HA_Component/ so custom_components/ is
importable directly.

    cd Apps/Game_Master/HA_Component
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
    """Enable custom integrations for every test in this suite."""
    yield


@pytest.fixture(autouse=True)
async def stub_external_integrations(hass, auto_enable_custom_integrations):
    """Stub core_configurator and shared_libraries as HA integrations.

    Game Master's manifest lists these as dependencies; they aren't installed
    in the test environment, so inject lightweight MockModule stubs after HA
    has discovered the real ``game_master`` package from this tree.
    """
    from homeassistant import loader as ha_loader
    from pytest_homeassistant_custom_component.common import MockModule, mock_integration

    await ha_loader.async_get_custom_components(hass)
    mock_integration(hass, MockModule("core_configurator"), built_in=False)
    mock_integration(hass, MockModule("shared_libraries"), built_in=False)
    yield
