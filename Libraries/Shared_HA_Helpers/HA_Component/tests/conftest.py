"""Pytest configuration for Shared HA Helpers tests.

Enables the hass fixture and custom integrations from
pytest-homeassistant-custom-component.

Run pytest from Libraries/Shared_HA_Helpers/HA_Component/ so that
custom_components/ is a direct child of the working directory and is
importable without any path manipulation. The pyproject.toml in that
directory sets testpaths and pythonpath for you.

    cd Libraries/Shared_HA_Helpers/HA_Component
    pytest
"""
import sys
from pathlib import Path

# Ensure custom_components/ is importable regardless of where pytest is
# invoked from (belt-and-suspenders alongside pyproject.toml pythonpath).
_ha_component_dir = Path(__file__).parent.parent
if str(_ha_component_dir) not in sys.path:
    sys.path.insert(0, str(_ha_component_dir))

import pytest

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable custom integrations for every test in this suite."""
    yield
