"""Constants for Shared HA Helpers.

Other integrations import helpers from http.py and mqtt.py directly.
This module holds only the domain name and the MQTT topic root so callers
never hard-code either string.
"""

DOMAIN = "shared_libraries"

# Root prefix for all Mission Control MQTT topics.
# Topic pattern: MC_TOPIC_ROOT/{kind}/…
# e.g.  mc/dnn/cmd/{device_id}
#       mc/tv/cmd/all
MC_TOPIC_ROOT = "mc"
