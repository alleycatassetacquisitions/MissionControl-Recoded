"""Pytest configuration for GBN HA tests."""
from __future__ import annotations

import sys
from pathlib import Path

_ha_component_dir = Path(__file__).parent.parent
if str(_ha_component_dir) not in sys.path:
    sys.path.insert(0, str(_ha_component_dir))

_repo_root = _ha_component_dir.parent.parent.parent
for extra in [
    _repo_root / "Libraries" / "Shared_HA_Helpers" / "HA_Component",
    _repo_root / "Apps" / "Core_Configurator" / "HA_Component",
]:
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))
