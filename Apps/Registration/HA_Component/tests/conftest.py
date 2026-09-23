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
_repo_root = _ha_component_dir.parent.parent.parent.parent  # MissionControl/
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
