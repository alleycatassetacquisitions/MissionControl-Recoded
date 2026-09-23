"""Constants for Core Configurator — source of truth for app endpoints."""

DOMAIN = "core_configurator"
EVENT_UPDATED = f"{DOMAIN}_updated"

# Stable keys other integrations and panels look up. Do not rename.
KEY_MASTER_CONTROL_SERVER = "master_control_server"
KEY_CENTRAL_PRIMARY = "central_primary"
KEY_CENTRAL_SECONDARY = "central_secondary"
KEY_ALLEYCATTV = "alleycattv"
KEY_GBN = "gbn"
KEY_PROXMOX = "proxmox"

SERVICE_CATALOG = (
    {
        "key": KEY_MASTER_CONTROL_SERVER,
        "label": "Master Control Server",
        "hint": "LAN address of MCS — the only Central HTTP adapter (Proxmox companion)",
        "apps": ["Registration"],
        "placeholder": "http://192.168.1.10:8700",
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
        "hint": "Hypervisor API (Bug Buster)",
        "apps": ["Bug Buster"],
        "placeholder": "https://192.168.1.1:8006",
        "extra_fields": (
            {"key": "node", "label": "Node name", "placeholder": "pve"},
        ),
    },
)

# Keys accepted from YAML import. Tokens stay in integration config entries, not here.
YAML_KEYS = (
    KEY_MASTER_CONTROL_SERVER,
    KEY_CENTRAL_PRIMARY,
    KEY_CENTRAL_SECONDARY,
    KEY_ALLEYCATTV,
    KEY_GBN,
    KEY_PROXMOX,
    "proxmox_node",
)
