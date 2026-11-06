import os
import socket
import uuid


def load_device_id(directory):
    os.makedirs(directory, mode=0o700, exist_ok=True)
    path = os.path.join(directory, "device-id")
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        pass
    else:
        with os.fdopen(descriptor, "w") as handle:
            handle.write(str(uuid.uuid4()) + "\n")
    with open(path, "r") as handle:
        return str(uuid.UUID(handle.read().strip()))


def advertised_host(settings):
    if settings["advertise_host"]:
        return settings["advertise_host"]
    if settings["discovery_interface"]:
        return settings["discovery_interface"]
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # Route selection only: no datagram is sent to this documentation address.
        probe.connect(("192.0.2.1", 9))
        return probe.getsockname()[0]
    except OSError:
        raise RuntimeError("Set CYBERVISUAL_ADVERTISE_HOST to the camera's LAN IPv4 address.")
    finally:
        probe.close()
