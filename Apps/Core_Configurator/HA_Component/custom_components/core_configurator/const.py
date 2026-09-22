"""Constants for Core Configurator — source of truth for app endpoints."""

DOMAIN = "core_configurator"
EVENT_UPDATED = f"{DOMAIN}_updated"

# Stable keys other integrations and panels look up. Do not rename.
KEY_REGISTRATION_PRIMARY = "registration_primary"
KEY_REGISTRATION_SECONDARY = "registration_secondary"
KEY_ALLEYCATTV = "alleycattv"
KEY_GBN = "gbn"
KEY_PROXMOX = "proxmox"

SERVICE_CATALOG = (
    {
        "key": KEY_REGISTRATION_PRIMARY,
        "label": "Registration · online",
        "hint": "Cloud / DigitalOcean player API",
        "apps": ["Registration"],
        "placeholder": "https://alleycat-dl83g.ondigitalocean.app",
    },
    {
        "key": KEY_REGISTRATION_SECONDARY,
        "label": "Registration · local",
        "hint": "LAN player API",
        "apps": ["Registration"],
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

# Keys accepted from YAML import. Tokens stay in Bug Buster config, not here.
YAML_KEYS = (
    KEY_REGISTRATION_PRIMARY,
    KEY_REGISTRATION_SECONDARY,
    KEY_ALLEYCATTV,
    KEY_GBN,
    KEY_PROXMOX,
    "proxmox_node",
)
