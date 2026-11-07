import ipaddress
from copy import deepcopy
from .pd42s1 import DEFAULT_PD42S1, validate_pd42s1


DEFAULT_SETTINGS = {
    "enabled": False,
    "advertise_host": "",
    "discovery_interface": "",
    "discovery_enabled": True,
    "rtsp_port": 8554,
    "encoder": "auto",
    "raw_fps": 30,
    "annotated_fps": 15,
    "raw_bitrate_kbps": 2000,
    "annotated_bitrate_kbps": 1000,
    "ptz_driver": "disabled",
    "pd42s1": deepcopy(DEFAULT_PD42S1),
}


def validate_settings(value):
    if not isinstance(value, dict) or set(value) - set(DEFAULT_SETTINGS):
        raise ValueError("network_camera must contain only documented, non-secret settings.")
    result = deepcopy(DEFAULT_SETTINGS)
    result.update(value)
    for key in ("enabled", "discovery_enabled"):
        if not isinstance(result[key], bool):
            raise ValueError("network_camera.%s must be a boolean." % key)
    for key, minimum, maximum in (("rtsp_port", 1024, 65535), ("raw_fps", 1, 30),
                                   ("annotated_fps", 1, 15), ("raw_bitrate_kbps", 64, 20000),
                                   ("annotated_bitrate_kbps", 64, 20000)):
        item = result[key]
        if isinstance(item, bool) or not isinstance(item, int) or not minimum <= item <= maximum:
            raise ValueError("network_camera.%s must be an integer in %d..%d." % (key, minimum, maximum))
    if result["encoder"] not in ("auto", "jetson", "software"):
        raise ValueError("network_camera.encoder must be auto, jetson, or software.")
    if result["ptz_driver"] not in ("disabled", "simulated", "pd42s1"):
        raise ValueError("network_camera.ptz_driver must be disabled, simulated or pd42s1.")
    result["pd42s1"] = validate_pd42s1(result["pd42s1"])
    for key in ("advertise_host", "discovery_interface"):
        item = result[key]
        if not isinstance(item, str):
            raise ValueError("network_camera.%s must be an IPv4 address." % key)
        if item:
            address = ipaddress.IPv4Address(item)
            if address.is_unspecified or address.is_multicast or str(address) == "255.255.255.255":
                raise ValueError("network_camera.%s must identify a unicast interface." % key)
    return result
