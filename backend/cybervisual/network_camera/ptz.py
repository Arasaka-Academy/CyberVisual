import json
import math
import os
import threading
import time
import uuid


class PTZError(ValueError):
    pass


class PTZUnavailable(PTZError):
    """An installed driver cannot safely execute movement yet."""


class PTZDriver(object):
    """A hardware adapter reports normalized pan/tilt coordinates and velocities.

    Implementations own calibration, physical limits, transport acknowledgements,
    and a movement watchdog. Raise PTZUnavailable when not ready, and PTZError
    for invalid movement arguments.
    """
    simulated = False

    def capabilities(self):
        raise NotImplementedError

    def status(self):
        raise NotImplementedError

    def absolute_move(self, pan, tilt):
        raise NotImplementedError

    def relative_move(self, pan, tilt):
        raise NotImplementedError

    def continuous_move(self, pan, tilt, timeout):
        raise NotImplementedError

    def stop(self):
        raise NotImplementedError


class SimulatedPTZDriver(PTZDriver):
    simulated = True

    def capabilities(self):
        return {"name": "CyberVisual simulated pan/tilt", "pan_tilt": True, "zoom": False,
                "absolute_move": True, "relative_move": True, "continuous_move": True,
                "position_range": [-1.0, 1.0], "velocity_range": [-1.0, 1.0]}

    def __init__(self, clock=None):
        self._clock = clock or time.monotonic
        self._lock = threading.RLock()
        self._position = [0.0, 0.0]
        self._velocity = [0.0, 0.0]
        self._updated = self._clock()
        self._deadline = self._updated

    def _advance(self):
        now = self._clock()
        elapsed = max(0, min(now, self._deadline) - self._updated)
        for axis in (0, 1):
            self._position[axis] = max(-1, min(1, self._position[axis] + self._velocity[axis] * elapsed))
            if abs(self._position[axis]) >= 1:
                self._velocity[axis] = 0.0
        if now >= self._deadline:
            self._velocity = [0.0, 0.0]
        self._updated = now

    def status(self):
        with self._lock:
            self._advance()
            return {"pan": self._position[0], "tilt": self._position[1],
                    "moving": any(self._velocity), "simulated": True}

    def absolute_move(self, pan, tilt):
        with self._lock:
            self.stop()
            self._position = [pan, tilt]

    def relative_move(self, pan, tilt):
        with self._lock:
            self._advance()
            self.absolute_move(max(-1, min(1, self._position[0] + pan)),
                               max(-1, min(1, self._position[1] + tilt)))

    def continuous_move(self, pan, tilt, timeout):
        with self._lock:
            self._advance()
            self._velocity = [pan, tilt]
            self._deadline = self._clock() + timeout

    def stop(self):
        with self._lock:
            self._advance()
            self._velocity = [0.0, 0.0]


class PTZController(object):
    def __init__(self, driver=None, state_path=None):
        self.driver = driver
        self.state_path = state_path
        self._lock = threading.RLock()
        self._presets = {}
        if state_path and os.path.isfile(state_path):
            with open(state_path, "r") as handle:
                self._presets = json.load(handle)

    @property
    def enabled(self):
        return self.driver is not None

    def _ready(self):
        if self.driver is None:
            raise PTZError("PTZ driver is disabled or not ready.")

    def status(self):
        self._ready()
        return self.driver.status()

    def capabilities(self):
        self._ready()
        return self.driver.capabilities()

    def absolute_move(self, pan, tilt):
        self._ready()
        self.driver.absolute_move(self._coordinate(pan), self._coordinate(tilt))

    def relative_move(self, pan, tilt):
        self._ready()
        self.driver.relative_move(self._coordinate(pan), self._coordinate(tilt))

    def continuous_move(self, pan, tilt, timeout=2.0):
        self._ready()
        if not math.isfinite(timeout) or not 0.1 <= timeout <= 30:
            raise PTZError("ContinuousMove timeout must be 0.1..30 seconds.")
        self.driver.continuous_move(self._coordinate(pan), self._coordinate(tilt), timeout)

    def stop(self):
        self._ready()
        self.driver.stop()

    def home(self):
        self.absolute_move(0.0, 0.0)

    def presets(self):
        self._ready()
        with self._lock:
            return [dict(value, token=key) for key, value in sorted(self._presets.items())]

    def set_preset(self, name, token=None):
        self._ready()
        with self._lock:
            if token and token not in self._presets:
                raise PTZError("Unknown preset token.")
            if len(self._presets) >= 32 and not token:
                raise PTZError("Preset limit reached.")
            if not isinstance(name, str) or not 1 <= len(name) <= 64:
                raise PTZError("Preset name must contain 1..64 characters.")
            token = token or uuid.uuid4().hex
            position = self.status()
            previous = dict(self._presets)
            self._presets[token] = {"name": name, "pan": position["pan"], "tilt": position["tilt"]}
            try:
                self._save()
            except Exception:
                self._presets = previous
                raise
            return token

    def goto_preset(self, token):
        self._ready()
        with self._lock:
            if token not in self._presets:
                raise PTZError("Unknown preset token.")
            preset = self._presets[token]
            self.absolute_move(preset["pan"], preset["tilt"])

    def remove_preset(self, token):
        self._ready()
        with self._lock:
            if token not in self._presets:
                raise PTZError("Unknown preset token.")
            previous = dict(self._presets)
            del self._presets[token]
            try:
                self._save()
            except Exception:
                self._presets = previous
                raise

    def _save(self):
        if self.state_path:
            os.makedirs(os.path.dirname(os.path.abspath(self.state_path)), exist_ok=True)
            temporary = self.state_path + ".tmp"
            with open(temporary, "w") as handle:
                json.dump(self._presets, handle, indent=2)
            os.replace(temporary, self.state_path)

    @staticmethod
    def _coordinate(value):
        if not isinstance(value, (int, float)) or not math.isfinite(value) or not -1 <= value <= 1:
            raise PTZError("Pan and tilt must be finite values in [-1, 1].")
        return float(value)
