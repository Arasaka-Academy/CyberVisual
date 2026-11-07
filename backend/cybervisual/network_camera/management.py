"""Dashboard facade for the same PTZ controller and event source as ONVIF."""
import math

from flask import jsonify, request

from .ptz import PTZError, PTZUnavailable


ACTIONS = {
    "absolute_move": ({"pan", "tilt"}, set()),
    "relative_move": ({"pan", "tilt"}, set()),
    "continuous_move": ({"pan", "tilt"}, set()),
    "stop": (set(), set()), "home": (set(), set()),
    "set_preset": ({"name"}, {"token"}),
    "goto_preset": ({"token"}, set()), "remove_preset": ({"token"}, set()),
}


def ptz_snapshot(camera):
    # Also held by reconfigure: never act on a replaced driver during a restart.
    with camera._lock:
        result = {"enabled": False, "driver": camera.settings["ptz_driver"],
                  "state": "disabled", "simulated": False, "position": None,
                  "capabilities": {}, "presets": [], "last_error": None,
                  "hardware_ready": False, "calibrated": False,
                  "calibration_required": camera.settings["ptz_driver"] == "pd42s1", "fault": None}
        controller = None
        try:
            controller = camera.ptz
            if not controller.enabled:
                return result
            result["enabled"] = True
            result.update(controller.readiness())
            position = controller.status()
            capabilities = controller.capabilities()
            presets = controller.presets()
            result.update(state="running", simulated=bool(controller.driver.simulated),
                          position=position if result["calibrated"] else None, capabilities=capabilities, presets=presets)
            if result["calibration_required"]:
                result.update(state="calibration_required", last_error="Confirm the current position as center before moving.")
        except Exception:
            result.update(state="unavailable", last_error="PTZ driver is not ready.")
            # A feedback/stop fault may have invalidated the reference during
            # status(). Return that new readiness in the same response.
            if controller is not None and controller.enabled:
                try:
                    result.update(controller.readiness())
                except Exception:
                    result.update(hardware_ready=False, calibrated=False, calibration_required=True)
            result["position"] = None
            result["last_error"] = {
                "serial_port_unconfigured": "Configure the PD42S1 serial port before calibration.",
                "configuration_required": "Configure axis geometry, limits, speed and verified enable feedback before calibration.",
                "serial_dependency_missing": "The PD42S1 serial driver dependency is missing.",
                "serial_connection_failed": "Check both PD42S1 addresses, serial connection and driver settings, then reconnect and calibrate.",
                "stop_unconfirmed": "Stop was not confirmed. Inspect both axes before reconnecting and calibrating.",
                "serial_feedback_lost": "Position feedback was lost. Inspect both axes and calibrate again.",
            }.get(result["fault"], result["last_error"])
        return result


def validate_command(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get("action"), str) or payload["action"] not in ACTIONS:
        raise PTZError("A documented PTZ action is required.")
    required, optional = ACTIONS[payload["action"]]
    fields = set(payload) - {"action"}
    if not required.issubset(fields) or fields - required - optional:
        raise PTZError("Invalid PTZ command arguments.")
    for axis in ("pan", "tilt"):
        if axis in payload:
            value = payload[axis]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not -1 <= value <= 1 or not math.isfinite(value):
                raise PTZError("Pan and tilt must be finite numbers in [-1, 1].")
    for key in ("name", "token"):
        if key in payload and (not isinstance(payload[key], str) or not 1 <= len(payload[key]) <= 64):
            raise PTZError("Preset name and token must contain 1..64 characters.")
    return payload["action"]


def register_management(app, runtime):
    @app.route("/api/ptz", methods=["GET"])
    def get_ptz():
        return jsonify(ptz_snapshot(runtime.network_camera))

    @app.route("/api/ptz/calibrate-center", methods=["POST"])
    def calibrate_ptz():
        payload = request.get_json(silent=True) if request.is_json else None
        if not isinstance(payload, dict) or set(payload) != {"confirm"} or payload["confirm"] is not True:
            return jsonify({"error": "Explicit center confirmation is required."}), 400
        try:
            camera = runtime.network_camera
            with camera._lock:
                camera.ptz.calibrate_center()
                return jsonify(ptz_snapshot(camera))
        except PTZUnavailable:
            return jsonify({"error": "Center calibration requires ready hardware and stationary axes."}), 503
        except PTZError as exc:
            return jsonify({"error": str(exc)}), 400
        except Exception:
            return jsonify({"error": "Center calibration could not be confirmed."}), 503

    @app.route("/api/ptz/command", methods=["POST"])
    def command_ptz():
        payload = request.get_json(silent=True) if request.is_json else None
        try:
            action = validate_command(payload)
            camera = runtime.network_camera
            with camera._lock:
                controller = camera.ptz
                if not controller.enabled:
                    raise PTZUnavailable("PTZ driver is disabled or not ready.")
                if action in ("absolute_move", "relative_move"):
                    getattr(controller, action)(payload["pan"], payload["tilt"])
                elif action == "continuous_move":
                    # Management UI renews the lease while held; never extend it
                    # to an arbitrary client-supplied duration.
                    controller.continuous_move(payload["pan"], payload["tilt"], timeout=2.0)
                elif action == "set_preset":
                    controller.set_preset(payload["name"], payload.get("token"))
                elif action in ("goto_preset", "remove_preset"):
                    getattr(controller, action)(payload["token"])
                else:
                    getattr(controller, action)()
                result = ptz_snapshot(camera)
                if result["state"] == "unavailable":
                    return jsonify({"error": result["last_error"]}), 503
                return jsonify(result)
        except PTZUnavailable:
            return jsonify({"error": "PTZ driver is disabled or not ready."}), 503
        except PTZError as exc:
            return jsonify({"error": str(exc)}), 400
        except Exception:
            return jsonify({"error": "PTZ operation could not be completed."}), 503

    @app.route("/api/events/recent", methods=["GET"])
    def recent_events():
        return jsonify(runtime.events.recent())
