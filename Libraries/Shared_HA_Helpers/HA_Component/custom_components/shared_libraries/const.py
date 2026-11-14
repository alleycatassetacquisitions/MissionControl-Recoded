"""Constants for Shared HA Helpers.

Other integrations import helpers from http.py and mqtt.py directly.
This module holds only the domain name and the MQTT topic root so callers
never hard-code either string.
"""

DOMAIN = "shared_libraries"

# Root prefix for all Mission Control MQTT topics.
# e.g. mc/dnn/cmd/device/{id}/page · mc/tv/cmd/all/stop
MC_TOPIC_ROOT = "mc"
