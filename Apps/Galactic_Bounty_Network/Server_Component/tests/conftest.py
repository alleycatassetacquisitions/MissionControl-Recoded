"""Disable pytest plugins that need Home Assistant (fcntl) on Windows."""

# Prevent pytest-homeassistant-custom-component from auto-loading.
pytest_plugins: list[str] = []
