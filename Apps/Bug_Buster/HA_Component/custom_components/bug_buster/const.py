"""Constants for Bug Buster — Proxmox console, MQTT spy, companion health, device logs."""

from datetime import timedelta

DOMAIN = "bug_buster"

CONF_VERIFY_SSL = "verify_ssl"
CONF_MQTT_TOPIC = "mqtt_topic"

DEFAULT_MQTT_TOPIC = "#"
DEFAULT_VERIFY_SSL = False
DEFAULT_LOGS_PER_PAGE = 20

# Guest list for console picker — not telemetry sensors (Core proxmoxve owns those).
POLL_INTERVAL = timedelta(seconds=30)
MQTT_BUFFER_SIZE = 200
MQTT_PREVIEW_CHARS = 2000
MQTT_HEX_BYTES = 64
TERM_PING_INTERVAL = 30

EVENT_HOSTS_UPDATE = f"{DOMAIN}_hosts_update"
EVENT_MQTT_MESSAGE = f"{DOMAIN}_mqtt_message"
EVENT_HEALTH_UPDATE = f"{DOMAIN}_health_update"

KEY_MCS = "master_control_server"
WS_DEVICE_LOGS = f"{DOMAIN}/device_logs"

# Companion services probed via shared_libraries.http.
HEALTH_KEYS = (
    KEY_MCS,
    "alleycattv",
    "gbn",
    "net_time",
)
