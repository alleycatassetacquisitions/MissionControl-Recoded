"""Constants for Core Configurator — source of truth for URLs and auth."""

DOMAIN = "core_configurator"
EVENT_UPDATED = f"{DOMAIN}_updated"

# Stable keys other integrations and panels look up. Do not rename.
KEY_MASTER_CONTROL_SERVER = "master_control_server"
KEY_CENTRAL_PRIMARY = "central_primary"
KEY_CENTRAL_SECONDARY = "central_secondary"
KEY_ALLEYCATTV = "alleycattv"
KEY_GBN = "gbn"
KEY_PROXMOX = "proxmox"

# Extra field keys stored under a service entry's ``extra`` dict.
EXTRA_TOKEN = "token"
EXTRA_NODE = "node"

# YAML / config-flow field that seeds the MCS Bearer into ``extra.token``.
YAML_MCS_TOKEN = "master_control_server_token"

SERVICE_CATALOG = (
    {
        "key": KEY_MASTER_CONTROL_SERVER,
        "label": "Master Control Server",
        "hint": "LAN address + API token — the only Central HTTP adapter (Proxmox companion)",
        "apps": ["Registration"],
        "placeholder": "http://192.168.1.10:8700",
        "extra_fields": (
            {
                "key": EXTRA_TOKEN,
                "label": "API token",
                "placeholder": "same value as MCS_API_TOKEN on the LXC",
                "sensitive": True,
            },
        ),
    },
    {
        "key": KEY_CENTRAL_PRIMARY,
        "label": "Central Server · online",
        "hint": "Read by Master Control Server — cloud / DigitalOcean player API",
        "apps": ["Master Control Server"],
        "placeholder": "https://alleycat-dl83g.ondigitalocean.app",
    },
    {
        "key": KEY_CENTRAL_SECONDARY,
        "label": "Central Server · local",
        "hint": "Read by Master Control Server — LAN player API fallback",
        "apps": ["Master Control Server"],
        "placeholder": "http://192.168.1.234:8090",
    },
    {
        "key": KEY_ALLEYCATTV,
        "label": "AlleycatTV streaming server",
        "hint": "Content API and media",
        "apps": ["AlleycatTV", "Content Manager", "Digital Node Nexus"],
        "placeholder": "http://headless-alleycat-streaming-server.local",
    },
    {
        "key": KEY_GBN,
        "label": "Galactic Bounty Network",
        "hint": "Poster capture and display server",
        "apps": ["GBN", "Registration posters"],
        "placeholder": "http://192.168.1.206:8100",
    },
    {
        "key": KEY_PROXMOX,
        "label": "Proxmox",
        "hint": "Hypervisor API — Bug Buster reads URL/node (and later tokens) from here",
        "apps": ["Bug Buster"],
        "placeholder": "https://192.168.1.1:8006",
        "extra_fields": (
            {"key": EXTRA_NODE, "label": "Node name", "placeholder": "pve"},
        ),
    },
)

# Keys accepted from YAML import. URLs and tokens both seed here once.
YAML_KEYS = (
    KEY_MASTER_CONTROL_SERVER,
    YAML_MCS_TOKEN,
    KEY_CENTRAL_PRIMARY,
    KEY_CENTRAL_SECONDARY,
    KEY_ALLEYCATTV,
    KEY_GBN,
    KEY_PROXMOX,
    "proxmox_node",
)
