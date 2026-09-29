"""Pytest configuration for Registration HA integration tests.

Run pytest from Apps/Registration/HA_Component/ so custom_components/ is
importable directly.

    cd Apps/Registration/HA_Component
    pytest
"""
import sys
from pathlib import Path

_ha_component_dir = Path(__file__).parent.parent
if str(_ha_component_dir) not in sys.path:
    sys.path.insert(0, str(_ha_component_dir))

# Also add the Core Configurator and Shared HA Helpers so imports resolve.
# HA_Component -> Registration -> Apps -> MissionControl
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

    Registration's manifest.json lists these as 'dependencies', so HA tries to
    set them up before loading Registration.  They aren't installed in the test
    environment, so we:

    1. Pre-trigger HA's custom-component discovery so DATA_CUSTOM_COMPONENTS is
       populated with the real 'registration' integration from this project.
    2. Inject lightweight MockModule stubs for the two dependency domains so
       HA's dependency-resolution machinery succeeds without a real install.

    Step 1 is critical: mock_integration uses setdefault(), which would create
    an empty dict if called before HA's own scan runs — causing HA to skip the
    filesystem discovery entirely and never find 'registration'.
    """
    from homeassistant import loader as ha_loader
    from pytest_homeassistant_custom_component.common import MockModule, mock_integration

    # Trigger HA's filesystem scan for custom components (idempotent if already done).
    await ha_loader.async_get_custom_components(hass)

    # Add stubs — they merge into the now-populated DATA_CUSTOM_COMPONENTS dict.
    mock_integration(hass, MockModule("core_configurator"), built_in=False)
    mock_integration(hass, MockModule("shared_libraries"), built_in=False)
    yield
