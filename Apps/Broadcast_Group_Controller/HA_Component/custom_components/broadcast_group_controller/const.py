"""Constants for Broadcast Group Controller."""

DOMAIN = "broadcast_group_controller"

STORAGE_VERSION = 1
STORAGE_KEY = f"{DOMAIN}.membership"

# Fabric kinds this controller can place / assign.
KIND_TV = "tv"
KIND_DNN = "dnn"
SUPPORTED_KINDS = (KIND_TV, KIND_DNN)

# Domain that owns the HA device registry entry for each kind.
KIND_DOMAIN = {
    KIND_TV: "alleycattv",
    KIND_DNN: "digital_node_nexus",
}

SERVICE_SET_AREA = "set_area"
SERVICE_SET_BROADCAST_GROUP = "set_broadcast_group"
SERVICE_CLEAR_BROADCAST_GROUP = "clear_broadcast_group"

WS_LIST_DEVICES = f"{DOMAIN}/list_devices"
WS_LIST_AREAS = f"{DOMAIN}/list_areas"
WS_GET_MEMBERSHIP = f"{DOMAIN}/get_membership"
