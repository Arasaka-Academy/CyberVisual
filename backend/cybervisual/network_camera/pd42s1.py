"""Feedback-supervised PD42S1 motion with a manually established reference."""
import math
import threading
import time

from .ptz import PTZDriver, PTZError, PTZUnavailable
from .pd42s1_serial import CommandCancelled, NativeSerialBus


PROTOCOL_SOURCE = "https://www.openedv.com/docs/industry/MotorDriver/PD42S1.html"
PROTOCOL_VERIFIED = True

AXIS_DEFAULTS = {"address": 1, "direction": 1, "counts_per_turn": 51200,
                 "gear_ratio": None, "minimum_degrees": None,
                 "maximum_degrees": None, "maximum_speed": None,
                 "enabled_feedback": None}
DEFAULT_PD42S1 = {"port": "", "baudrate": 115200,
                  "pan": dict(AXIS_DEFAULTS),
                  "tilt": dict(AXIS_DEFAULTS, address=2)}


def validate_pd42s1(value):
    from copy import deepcopy
    if not isinstance(value, dict) or set(value) - set(DEFAULT_PD42S1):
        raise ValueError("pd42s1 contains undocumented settings.")
    result = deepcopy(DEFAULT_PD42S1)
    result.update(value)
    if not isinstance(result["port"], str) or (result["port"] and
            (not result["port"].startswith("/dev/") or ".." in result["port"].split("/") or
             any(ord(c) < 32 for c in result["port"]))):
        raise ValueError("pd42s1.port must be an explicit /dev serial device.")
    if result["baudrate"] != 115200 or isinstance(result["baudrate"], bool):
        raise ValueError("pd42s1 currently requires the planned 115200 8N1 configuration.")
    for axis in ("pan", "tilt"):
        item = result[axis]
        if not isinstance(item, dict) or set(item) - set(AXIS_DEFAULTS):
            raise ValueError("Invalid pd42s1 axis settings.")
        merged = dict(DEFAULT_PD42S1[axis], **item)
        if isinstance(merged["address"], bool) or not isinstance(merged["address"], int) or not 1 <= merged["address"] <= 255:
            raise ValueError("Each PD42S1 requires a unicast address in 1..255.")
        if isinstance(merged["direction"], bool) or merged["direction"] not in (-1, 1):
            raise ValueError("Axis direction must be -1 or 1.")
        if merged["enabled_feedback"] is not None and (isinstance(merged["enabled_feedback"], bool) or
                not isinstance(merged["enabled_feedback"], int) or merged["enabled_feedback"] not in (0, 1)):
            raise ValueError("Confirm the enabled feedback bit (0 or 1) on the installed firmware.")
        for key in ("counts_per_turn", "gear_ratio", "maximum_speed"):
            number = merged[key]
            if number is not None and (isinstance(number, bool) or not isinstance(number, (int, float)) or not math.isfinite(number) or number <= 0 or number > 1e9):
                raise ValueError("Axis counts, ratio and speed must be positive finite values.")
        low, high = merged["minimum_degrees"], merged["maximum_degrees"]
        for number in (low, high):
            if number is not None and (isinstance(number, bool) or not isinstance(number, (int, float)) or not math.isfinite(number) or abs(number) > 360):
                raise ValueError("Axis limits must be finite degrees within one turn.")
        if low is not None and low >= 0 or high is not None and high <= 0:
            raise ValueError("Axis limits must enclose the manually calibrated center.")
        result[axis] = merged
    if result["pan"]["address"] == result["tilt"]["address"]:
        raise ValueError("Pan and tilt must use different RS485 addresses.")
    return result


class PD42S1Driver(PTZDriver):
    """Feedback-based finite-step supervisor over one native serial bus.

    A bus must serialize transactions, validate each reply, never replay motion,
    and provide read_axes(), move_finite(address, counts, counts_per_second),
    stop_hold(address), close(). stop_hold MUST retain holding torque.
    """
    STEP_SECONDS = 0.2

    def __init__(self, settings, bus=None, clock=None, start_worker=True):
        self.settings = validate_pd42s1(settings)
        self._bus = bus
        self._owns_bus = bus is None
        self._clock = clock or time.monotonic
        self._lock = threading.RLock()
        self._stopping = threading.Event()
        self._closed = threading.Event()
        self._center = None
        self._target = None
        self._velocity = None
        self._deadline = 0
        self._fault = None
        self._expected = None
        self._pending = {}
        self._thread = None
        if self._owns_bus:
            self._open_bus()
        if start_worker:
            self._thread = threading.Thread(target=self._run, name="pd42s1-motion", daemon=True)
            self._thread.start()

    def _open_bus(self):
        self._center = self._expected = None
        self._target = self._velocity = None
        self._pending = {}
        if self._bus is not None:
            self._bus.close()
            self._bus = None
        if not self.settings["port"]:
            self._fault = "serial_port_unconfigured"
            return
        try:
            self._configured()
            self._bus = NativeSerialBus(self.settings)
            self._fault = None
        except (PTZUnavailable, ValueError):
            self._fault = "configuration_required"
        except ImportError:
            self._fault = "serial_dependency_missing"
        except Exception:
            self._fault = "serial_connection_failed"

    def capabilities(self):
        return {"name": "PD42S1 RS485 pan/tilt", "pan_tilt": True, "zoom": False,
                "absolute_move": True, "relative_move": True, "continuous_move": True,
                "position_range": [-1.0, 1.0], "velocity_range": [-1.0, 1.0]}

    def readiness(self):
        with self._lock:
            return {"hardware_ready": self._bus is not None and self._fault is None and not self._closed.is_set(),
                    "calibrated": self._center is not None, "calibration_required": self._center is None,
                    "fault": self._fault}

    def _configured(self):
        for axis in ("pan", "tilt"):
            if any(self.settings[axis][key] is None for key in AXIS_DEFAULTS):
                raise PTZUnavailable("Configure axis counts, ratio, limits and speed before calibration.")

    def _ready(self, calibrated=True):
        if self._closed.is_set() or self._bus is None or self._fault:
            raise PTZUnavailable("PD42S1 is unavailable; check configuration and the serial connection.")
        self._configured()
        if calibrated and self._center is None:
            raise PTZUnavailable("Confirm the current position as center before moving.")

    def _feedback(self):
        try:
            feedback = self._bus.read_axes()
            if len(feedback) != 2:
                raise ValueError("Missing axis feedback")
            for axis, item in zip(("pan", "tilt"), feedback):
                if item["address"] != self.settings[axis]["address"] or not isinstance(item["moving"], bool) or not math.isfinite(item["counts"]):
                    raise ValueError("Invalid axis feedback")
            if self._center is not None and self._expected is not None:
                for index, item in enumerate(feedback):
                    low, high = self._expected[index]
                    # A reset or manual displacement invalidates the software
                    # reference. Never chase unexpected feedback with a target.
                    if not low - 2 <= item["counts"] <= high + 2:
                        axis = self.settings[("pan", "tilt")[index]]
                        degrees = self._degrees(index, item["counts"])
                        self._fault = ("position_outside_limits" if degrees < axis["minimum_degrees"] - 0.1 or
                                       degrees > axis["maximum_degrees"] + 0.1 else "reference_discontinuity")
                        raise ValueError("Unexpected displacement")
            return feedback
        except CommandCancelled:
            raise
        except Exception:
            self._center = self._target = self._velocity = None
            self._fault = self._fault or "serial_feedback_lost"
            self._stopping.set()
            request_stop = getattr(self._bus, "request_stop", None)
            if request_stop is not None:
                request_stop()
            raise PTZUnavailable("PD42S1 feedback was lost; stop and recalibrate after reconnecting.")

    def _degrees(self, index, counts):
        axis = self.settings[("pan", "tilt")[index]]
        return (counts - self._center[index]) * axis["direction"] * 360.0 / (axis["counts_per_turn"] * axis["gear_ratio"])

    def _counts(self, index, degrees):
        axis = self.settings[("pan", "tilt")[index]]
        return int(round(self._center[index] + degrees * axis["direction"] * axis["counts_per_turn"] * axis["gear_ratio"] / 360.0))

    def status(self):
        with self._lock:
            self._ready(False)
            feedback = self._feedback()
            if self._center is None:
                return {"pan": 0.0, "tilt": 0.0, "moving": any(item["moving"] for item in feedback), "simulated": False, "position_known": False}
            position = []
            for index, item in enumerate(feedback):
                axis = self.settings[("pan", "tilt")[index]]
                degrees = self._degrees(index, item["counts"])
                if degrees < axis["minimum_degrees"] - 0.1 or degrees > axis["maximum_degrees"] + 0.1:
                    self._fault, self._center = "position_outside_limits", None
                    raise PTZUnavailable("Feedback is outside configured mechanical limits.")
                position.append(degrees / (axis["maximum_degrees"] if degrees >= 0 else -axis["minimum_degrees"]))
            return {"pan": position[0], "tilt": position[1], "moving": any(item["moving"] for item in feedback), "simulated": False, "position_known": True}

    def calibrate_center(self):
        with self._lock:
            if self._owns_bus and (self._bus is None or self._fault):
                self._open_bus()
            self._ready(False)
            self._center = self._expected = None
            self.stop()
            feedback = self._feedback()
            if any(item["moving"] for item in feedback):
                raise PTZUnavailable("Both axes must be stationary before confirming center.")
            center = tuple(item["counts"] for item in feedback)
            for index, name in enumerate(("pan", "tilt")):
                axis = self.settings[name]
                for limit in (axis["minimum_degrees"], axis["maximum_degrees"]):
                    endpoint = center[index] + limit * axis["direction"] * axis["counts_per_turn"] * axis["gear_ratio"] / 360.0
                    if not -0x80000000 <= endpoint <= 0x7FFFFFFF:
                        self._fault = "configuration_required"
                        raise PTZUnavailable("Configured mechanical travel exceeds signed native position feedback.")
            self._center = center
            self._expected = [(item["counts"], item["counts"]) for item in feedback]

    def _resume(self):
        resume = getattr(self._bus, "resume", None)
        if resume is not None:
            resume()
        self._stopping.clear()

    def absolute_move(self, pan, tilt):
        with self._lock:
            self._ready()
            self._resume()
            self._velocity = None
            self._target = (pan, tilt)

    def relative_move(self, pan, tilt):
        with self._lock:
            position = self.status()
            self.absolute_move(max(-1, min(1, position["pan"] + pan)), max(-1, min(1, position["tilt"] + tilt)))

    def continuous_move(self, pan, tilt, timeout):
        if not 0.1 <= timeout <= 2:
            raise PTZError("Continuous movement lease must be at most 2 seconds.")
        with self._lock:
            self._ready()
            self._resume()
            self._target = None
            self._velocity = (pan, tilt)
            self._deadline = self._clock() + timeout

    def stop(self):
        # Cancel before taking the bus lock; a stop supersedes queued targets.
        self._stopping.set()
        if self._bus is not None:
            request_stop = getattr(self._bus, "request_stop", None)
            if request_stop is not None:
                request_stop()
        with self._lock:
            self._target = self._velocity = None
            self._pending = {}
            if self._bus is None:
                raise PTZUnavailable("PD42S1 serial connection is unavailable.")
            try:
                failures = []
                for axis in ("pan", "tilt"):
                    try:
                        self._bus.stop_hold(self.settings[axis]["address"])
                    except Exception as exc:
                        failures.append(exc)
                # Try both axes even when the first address fails.
                if failures or any(item["moving"] for item in self._feedback()):
                    raise PTZUnavailable("Stop feedback still reports movement.")
                if self._center is not None:
                    self._expected = [(item["counts"], item["counts"]) for item in self._feedback()]
            except Exception:
                self._fault, self._center = "stop_unconfirmed", None
                raise PTZUnavailable("PD42S1 stop was not confirmed; inspect both axes.")

    def _step(self):
        with self._lock:
            if self._stopping.is_set() or self._closed.is_set() or self._fault or self._center is None:
                return
            if self._velocity is not None and self._clock() >= self._deadline:
                self.stop()
                return
            if self._velocity is None and self._target is None:
                # Keep supervising an idle calibrated reference as well.
                self._feedback()
                return
            try:
                feedback = self._feedback()
            except CommandCancelled:
                return
            # Wait for the previous finite targets to finish. No queued relative
            # movement can accumulate if the process or serial connection dies.
            for index, (counts, deadline) in list(self._pending.items()):
                if not feedback[index]["moving"] and abs(feedback[index]["counts"] - counts) <= 2:
                    del self._pending[index]
                elif self._clock() >= deadline:
                    self._fault, self._center = "finite_target_unconfirmed", None
                    raise PTZUnavailable("Finite movement did not reach its target.")
            if self._pending:
                return
            if any(item["moving"] for item in feedback):
                return
            finished = True
            for index, item in enumerate(feedback):
                if self._stopping.is_set():
                    return
                axis = self.settings[("pan", "tilt")[index]]
                current = self._degrees(index, item["counts"])
                if not axis["minimum_degrees"] - 0.1 <= current <= axis["maximum_degrees"] + 0.1:
                    self._fault, self._center = "position_outside_limits", None
                    raise PTZUnavailable("Feedback is outside configured mechanical limits.")
                velocity = self._velocity[index] if self._velocity is not None else 1.0
                distance = axis["maximum_speed"] * self.STEP_SECONDS
                target = (current + velocity * distance if self._velocity is not None else
                          self._target[index] * (axis["maximum_degrees"] if self._target[index] >= 0 else -axis["minimum_degrees"]))
                target = max(axis["minimum_degrees"], min(axis["maximum_degrees"], target))
                next_position = max(current - distance, min(current + distance, target))
                counts = self._counts(index, next_position)
                if counts != item["counts"]:
                    finished = False
                    speed = max(1, int(axis["maximum_speed"] * axis["counts_per_turn"] * axis["gear_ratio"] / 360.0))
                    # Non-idempotent motion is issued once. Exceptions invalidate
                    # reference; the next loop never automatically replays it.
                    try:
                        self._expected[index] = (min(item["counts"], counts), max(item["counts"], counts))
                        self._bus.move_finite(axis["address"], counts, speed)
                        self._pending[index] = (counts, self._clock() + 1.5)
                    except CommandCancelled:
                        return
                    except Exception:
                        self._fault, self._center = "serial_motion_failed", None
                        self._target = self._velocity = None
                        raise PTZUnavailable("PD42S1 movement acknowledgement was lost; movement was not replayed.")
            if finished and self._velocity is None:
                self._target = None

    def _run(self):
        while not self._closed.wait(0.05):
            try:
                self._step()
            except CommandCancelled:
                continue
            except Exception:
                with self._lock:
                    self._fault, self._center = self._fault or "serial_motion_failed", None
                    self._target = self._velocity = None
                try:
                    self.stop()
                except PTZError:
                    pass

    def close(self):
        self._closed.set()
        try:
            if self._bus is not None:
                self.stop()
        finally:
            if self._thread:
                self._thread.join(timeout=2)
            if self._bus is not None:
                self._bus.close()
