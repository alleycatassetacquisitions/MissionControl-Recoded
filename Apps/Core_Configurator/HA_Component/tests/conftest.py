"""Pytest configuration for Core Configurator tests.

Enables the hass fixture and custom integrations from
pytest-homeassistant-custom-component.
"""
import pytest

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable custom integrations for every test in this suite."""
    yield
