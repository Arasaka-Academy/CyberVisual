import logging
import os
import threading
import time

from flask import Response, request
import numpy as np
from PIL import Image

from ..overlay import encode_jpeg
from .auth import DeviceCredentials
from .discovery import DiscoveryResponder
from .events import SubscriptionError
from .identity import advertised_host, load_device_id
from .onvif_device import device_request
from .onvif_events import events_request
from .onvif_media import media_request
from .onvif_ptz import ptz_request
from .ptz import PTZController, PTZError, PTZUnavailable, SimulatedPTZDriver
from .rtsp import RTSPServer
from .soap import NS, SOAPFault, envelope, parse_xml, q, text


LOGGER = logging.getLogger(__name__)


class NetworkCameraService(object):
    def __init__(self, runtime):
        self.runtime = runtime
        self.settings = runtime.get_config()["network_camera"]
        self.credentials = DeviceCredentials.from_environment()
        self.state_dir = os.environ.get("CYBERVISUAL_STATE_DIR", os.path.abspath(".cybervisual"))
        self.http_port = int(os.environ.get("CYBERVISUAL_PORT", "8000"))
        self._lock = threading.RLock()
        self._identity_lock = threading.RLock()
        self._device_id = self._host = self._ptz = None
        self._rtsp = self._discovery = None
        self._started = False
        self._state = "stopped" if self.settings["enabled"] else "disabled"
        self._error = self._discovery_error = None

    @property
    def device_id(self):
        self._prepare()
        return self._device_id

    @property
    def host(self):
        self._prepare()
        return self._host

    @property
    def ptz(self):
        self._prepare()
        return self._ptz

    def _prepare(self):
        with self._identity_lock:
            if self._device_id is None:
                self._device_id = load_device_id(self.state_dir)
            if self._host is None:
                self._host = advertised_host(self.settings)
            if self._ptz is None:
                simulated = self.settings["enabled"] and self.settings["ptz_driver"] == "simulated"
                self._ptz = PTZController(SimulatedPTZDriver() if simulated else None,
                                          os.path.join(self.state_dir, "ptz-presets.json"))

    def http_url(self, path):
        return "http://%s:%d%s" % (self.host, self.http_port, path)

    def rtsp_url(self, profile):
        return "rtsp://%s:%d/%s" % (self.host, self.settings["rtsp_port"], profile)

    def scopes(self):
        result = ["onvif://www.onvif.org/type/video_encoder", "onvif://www.onvif.org/name/CyberVisual",
                  "onvif://www.onvif.org/hardware/CyberVisual"]
        if self.ptz.enabled:
            result.append("onvif://www.onvif.org/type/ptz")
        return result

    def start(self):
        with self._lock:
            if self._started:
                return
            self._started = True
            if not self.settings["enabled"]:
                self._state = "disabled"
                return
            self._state, self._error = "starting", None
            if not self.credentials.configured:
                self._state = "error"
                self._error = "Configure the ONVIF device username and password before enabling network camera output."
                return
            try:
                self._prepare()
                self._rtsp = RTSPServer(self.runtime, self.settings, self.credentials)
                self._rtsp.start()
                self._state = "running"
            except Exception as exc:
                if self._rtsp:
                    self._rtsp.stop()
                self._rtsp = None
                self._state, self._error = "error", str(exc)
                LOGGER.warning("Network camera output could not start: %s", self._error)
                return
            if self.settings["discovery_enabled"]:
                try:
                    self._discovery = DiscoveryResponder(self, self.settings["discovery_interface"])
                    self._discovery.start()
                except OSError:
                    if self._discovery:
                        self._discovery.stop()
                    self._discovery = None
                    self._state = "degraded"
                    self._discovery_error = "Unable to join WS-Discovery on the configured IPv4 interface."

    def stop(self):
        with self._lock:
            if self._discovery:
                self._discovery.stop()
                self._discovery = None
            if self._rtsp:
                self._rtsp.stop()
                self._rtsp = None
            if self._ptz and self._ptz.enabled:
                self._ptz.stop()
            self.runtime.events.close()
            self._started = False
            self._state = "stopped" if self.settings["enabled"] else "disabled"

    def reconfigure(self, previous, candidate):
        if all(previous.get(key) == candidate.get(key) for key in ("network_camera", "resolution", "camera_fps")):
            return
        with self._lock:
            was_started = self._started
            self.stop()
            self.settings = candidate["network_camera"]
            with self._identity_lock:
                self._host = self._ptz = None
            self._error = self._discovery_error = None
            self._state = "stopped" if self.settings["enabled"] else "disabled"
            if was_started:
                self.start()

    def status(self):
        # Do not hold the lifecycle lock while joining workers or making status requests.
        rtsp = self._rtsp
        output = rtsp.status() if rtsp else {"encoder": None, "streams": {}}
        position = None
        if self._ptz and self._ptz.enabled:
            position = self._ptz.status()
        ready = self._host is not None
        profiles = []
        for token, name in (("raw", "Original"), ("annotated", "AI annotated")):
            stream = output["streams"].get(token, {})
            profiles.append(dict(stream, token=token, name=name,
                                 rtsp_uri=self.rtsp_url(token) if ready else None,
                                 snapshot_uri=self.http_url("/onvif/snapshot/" + token) if ready else None))
        return {"enabled": self.settings["enabled"], "state": self._state,
                "credentials_configured": self.credentials.configured, "device_uuid": self._device_id,
                "onvif_url": self.http_url("/onvif/device_service") if ready else None,
                "encoder": output["encoder"], "profiles": profiles, "last_error": self._error,
                "discovery": {"state": "running" if self._discovery else "error" if self._discovery_error else "disabled",
                              "last_error": self._discovery_error},
                "events": self.runtime.events.status(),
                "ptz": {"enabled": bool(self._ptz and self._ptz.enabled), "driver": self.settings["ptz_driver"],
                        "simulated": bool(position and position.get("simulated")), "position": position}}

    def register(self, app):
        for path, prefix in (("device_service", "tds"), ("media_service", "trt"), ("media2_service", "tr2"),
                             ("events_service", "tev"), ("ptz_service", "tptz")):
            app.add_url_rule("/onvif/" + path, "onvif_" + prefix,
                             lambda prefix=prefix: self._soap(prefix), methods=["POST"])
        app.add_url_rule("/onvif/subscriptions/<token>", "onvif_pullpoint",
                         lambda token: self._soap("tev", token), methods=["POST"])
        app.add_url_rule("/onvif/snapshot/<profile>", "onvif_snapshot", self._snapshot, methods=["GET"])

    def _digest(self):
        uri = request.path + ("?" + request.query_string.decode("latin1") if request.query_string else "")
        return self.credentials.verify_digest(request.method, uri, request.headers.get("Authorization"))

    def _soap(self, prefix, subscription=None):
        if not self.settings["enabled"]:
            return Response(status=404)
        try:
            root = parse_xml(request.stream.read(262145))
            body = root.find("s:Body", NS)
            if root.tag != q("s:Envelope") or body is None or len(body) != 1:
                raise SOAPFault("ter:InvalidArgVal", "A SOAP 1.2 envelope with one operation is required.")
            command = body[0]
            namespace, operation = command.tag[1:].split("}", 1) if command.tag.startswith("{") else ("", command.tag)
            allowed = (NS["tev"], NS["wsnt"]) if prefix == "tev" else (NS[prefix],)
            if namespace not in allowed:
                raise SOAPFault("ter:ActionNotSupported", "Operation does not belong to this service.")
            header = root.find("s:Header", NS)
            clock_query = prefix == "tds" and operation == "GetSystemDateAndTime"
            if not clock_query and not self._digest() and not (header is not None and self.credentials.verify_wsse(header)):
                raise SOAPFault("ter:NotAuthorized", "Device authentication is required.", 401)
            self._prepare()
            if prefix == "tds":
                result = device_request(self, operation, command)
            elif prefix in ("trt", "tr2"):
                result = media_request(self, prefix, operation, command)
            elif prefix == "tev":
                result = events_request(self, operation, command, subscription)
            else:
                result = ptz_request(self, operation, command)
            action = response_action(prefix, namespace, operation)
            payload = envelope(result, action, text(root, "s:Header/wsa:MessageID"))
            return Response(payload, content_type='application/soap+xml; charset=utf-8; action="%s"' % action)
        except SOAPFault as exc:
            response = Response(exc.xml(), status=exc.status, content_type="application/soap+xml; charset=utf-8")
            if exc.status == 401:
                response.headers["WWW-Authenticate"] = self.credentials.challenge()
            return response
        except PTZUnavailable:
            fault = SOAPFault("ter:ServiceNotAvailable", "PTZ driver is not ready.", 503)
            return Response(fault.xml(), status=503, content_type="application/soap+xml; charset=utf-8")
        except (ValueError, PTZError, SubscriptionError):
            fault = SOAPFault("ter:InvalidArgVal", "Invalid request argument, token, or subscription.")
            return Response(fault.xml(), status=400, content_type="application/soap+xml; charset=utf-8")
        except Exception:
            LOGGER.exception("ONVIF service operation failed")
            fault = SOAPFault("ter:ServiceNotAvailable", "Device service is unavailable.", 503)
            return Response(fault.xml(), status=503, content_type="application/soap+xml; charset=utf-8")

    def _snapshot(self, profile):
        if not self.settings["enabled"] or profile not in ("raw", "annotated"):
            return Response(status=404)
        if not self._digest():
            return Response(status=401, headers={"WWW-Authenticate": self.credentials.challenge()})
        buffer = self.runtime.raw_buffer if profile == "raw" else self.runtime.buffer
        item = buffer.snapshot()
        if not item["valid"] or item["frame"] is None or time.time() - item["frame_ts"] > 5:
            return Response("No fresh frame available.", status=503)
        config = self.runtime.get_config()
        width, height = config["resolution"]["width"], config["resolution"]["height"]
        frame, jpeg = item["frame"], item["jpeg"]
        if frame.shape[:2] != (height, width):
            resampling = getattr(Image, "Resampling", Image)
            frame = np.asarray(Image.fromarray(frame).resize((width, height), resampling.BILINEAR))
            jpeg = None
        jpeg = jpeg or encode_jpeg(frame, config["jpeg_quality"])
        return Response(jpeg, mimetype="image/jpeg", headers={"Cache-Control": "no-store"})


def response_action(prefix, namespace, operation):
    if prefix == "tev":
        if operation in ("Renew", "Unsubscribe"):
            return "http://docs.oasis-open.org/wsn/bw-2/SubscriptionManager/" + operation + "Response"
        port = "PullPointSubscription" if operation in ("PullMessages", "SetSynchronizationPoint") else "EventPortType"
        return NS["tev"] + "/" + port + "/" + operation + "Response"
    return namespace + "/" + operation + "Response"
