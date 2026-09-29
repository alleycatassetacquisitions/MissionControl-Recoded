"""Pytest configuration for Broadcast Group Controller HA tests."""
from __future__ import annotations

import sys
from pathlib import Path

_ha_component_dir = Path(__file__).parent.parent
if str(_ha_component_dir) not in sys.path:
    sys.path.insert(0, str(_ha_component_dir))

_repo_root = _ha_component_dir.parent.parent.parent
for extra in [
    _repo_root / "Libraries" / "Shared_HA_Helpers" / "HA_Component",
]:
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

import pytest

try:
    import fcntl  # noqa: F401

    _HA_AVAILABLE = True
except ImportError:
    _HA_AVAILABLE = False

if _HA_AVAILABLE:
    pytest_plugins = "pytest_homeassistant_custom_component"

    @pytest.fixture(autouse=True)
    def auto_enable_custom_integrations(enable_custom_integrations):
        yield

    @pytest.fixture(autouse=True)
    async def stub_external_integrations(hass, auto_enable_custom_integrations):
        from homeassistant import loader as ha_loader
        from pytest_homeassistant_custom_component.common import (
            MockModule,
            mock_integration,
        )

        await ha_loader.async_get_custom_components(hass)
        mock_integration(hass, MockModule("shared_libraries"), built_in=False)
        mock_integration(hass, MockModule("mqtt"), built_in=False)
        yield
else:

    @pytest.fixture(autouse=True)
    def _skip_hass_tests(request):
        if request.node.get_closest_marker("asyncio") or "hass" in getattr(
            request, "fixturenames", ()
        ):
            pytest.skip("Home Assistant pytest plugin requires Unix (fcntl)")
        yield
