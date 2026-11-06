import socket
import threading
import time
import uuid

from .soap import NS, SOAPFault, add, node, parse_xml, q, serialize, text


GROUP = "239.255.255.250"


class DiscoveryResponder(object):
    def __init__(self, camera, interface="", port=3702):
        self.camera, self.interface, self.port = camera, interface, port
        self._socket = None
        self._thread = None
        self._stop = threading.Event()
        self._sequence = 0
        self._instance = int(time.time())

    def start(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("", self.port))
            interface = socket.inet_aton(self.interface or self.camera.host)
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, socket.inet_aton(GROUP) + interface)
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, interface)
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 1)
            sock.settimeout(0.25)
        except Exception:
            sock.close()
            raise
        self._socket = sock
        self._stop.clear()
        self._announce("Hello")
        self._thread = threading.Thread(target=self._run, name="cybervisual-discovery")
        self._thread.daemon = True
        self._thread.start()

    def _run(self):
        while not self._stop.is_set():
            try:
                data, address = self._socket.recvfrom(8193)
                response = self.respond(data)
                if response:
                    self._socket.sendto(response, address)
            except socket.timeout:
                pass
            except (OSError, SOAPFault, ValueError):
                if self._stop.is_set():
                    return

    def respond(self, data):
        if len(data) > 8192:
            return None
        root = parse_xml(data)
        body = root.find("s:Body", NS)
        if body is None or len(body) != 1:
            return None
        command = body[0]
        if command.tag == q("d:Probe"):
            types = text(command, "d:Types", "").split()
            if any(value.split(":")[-1] not in ("NetworkVideoTransmitter", "Device") for value in types):
                return None
            requested = command.find("d:Scopes", NS)
            if requested is not None:
                match_by = requested.get("MatchBy", NS["d"] + "/rfc3986")
                if match_by != NS["d"] + "/rfc3986":
                    return None
                for scope in (requested.text or "").split():
                    if not any(item == scope or item.startswith(scope.rstrip("/") + "/") for item in self.camera.scopes()):
                        return None
            kind = "ProbeMatches"
        elif command.tag == q("d:Resolve"):
            if text(command, "a:EndpointReference/a:Address") != "urn:uuid:" + self.camera.device_id:
                return None
            kind = "ResolveMatches"
        else:
            return None
        relates = text(root, "s:Header/a:MessageID") or text(root, "s:Header/wsa:MessageID")
        return self._message(kind, relates)

    def _message(self, kind, relates=None):
        root = node("s:Envelope")
        header = add(root, "s:Header")
        add(header, "a:Action", NS["d"] + "/" + kind)
        add(header, "a:MessageID", "urn:uuid:" + str(uuid.uuid4()))
        add(header, "a:To", "http://schemas.xmlsoap.org/ws/2004/08/addressing/role/anonymous"
            if relates else "urn:schemas-xmlsoap-org:ws:2005:04:discovery")
        if relates:
            add(header, "a:RelatesTo", relates)
        self._sequence += 1
        add(header, "d:AppSequence", InstanceId=self._instance, MessageNumber=self._sequence)
        message = add(add(root, "s:Body"), "d:" + kind)
        if kind in ("ProbeMatches", "ResolveMatches"):
            message = add(message, "d:" + ("ProbeMatch" if kind == "ProbeMatches" else "ResolveMatch"))
        add(add(message, "a:EndpointReference"), "a:Address", "urn:uuid:" + self.camera.device_id)
        if kind != "Bye":
            add(message, "d:Types", "dn:NetworkVideoTransmitter")
            add(message, "d:Scopes", " ".join(self.camera.scopes()))
            add(message, "d:XAddrs", self.camera.http_url("/onvif/device_service"))
        add(message, "d:MetadataVersion", 1)
        return serialize(root)

    def _announce(self, kind):
        try:
            self._socket.sendto(self._message(kind), (GROUP, self.port))
        except OSError:
            pass

    def stop(self):
        self._stop.set()
        if self._socket:
            self._announce("Bye")
            self._socket.close()
        if self._thread:
            self._thread.join(timeout=1)
        self._socket = None
