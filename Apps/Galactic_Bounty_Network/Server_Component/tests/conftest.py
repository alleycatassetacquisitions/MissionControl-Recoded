"""GBN server tests are FastAPI-only — do not load HA pytest plugins.

The HA plugin entry point is named ``homeassistant``; disable it via
``pytest.ini`` (``-p no:homeassistant``). An empty ``pytest_plugins`` here
does not unregister entry-point plugins.
"""
