"""PD42S1 native V1.2 protocol, Python 3.6 compatible.

Source and discrepancies are recorded in docs/pd42s1.md. Only read commands
and bounded relative position targets are exposed. No parameter writes,
unbounded velocity mode, driver reset, brake latch, or disable command.
"""
import math
import queue
import struct
import threading
import time
from concurrent.futures import Future


COUNTS_PER_TURN = 51200
STEP_SECONDS = 0.2
# Data lengths include the result byte. The wire protocol has no length field.
REPLY_LENGTHS = {0x20: 3, 0x2A: 5, 0x2C: 2, 0x2F: 2, 0x30: 2,
                 0x32: 45, 0x94: 18, 0xF3: 1}
REQUEST_LENGTHS = {code: 0 for code in REPLY_LENGTHS}
REQUEST_LENGTHS[0xF3] = 8


class SerialProtocolError(IOError):
    pass


class CommandCancelled(IOError):
    """A stop superseded an operation which has not reached the wire."""


def encode_frame(address, code, payload=b""):
    if not isinstance(address, int) or isinstance(address, bool) or not 1 <= address <= 255:
        raise ValueError("Only individual PD42S1 addresses 1..255 are allowed.")
    if code not in REQUEST_LENGTHS or len(payload) != REQUEST_LENGTHS[code]:
        raise ValueError("Unsupported native command or invalid payload length.")
    body = bytes((0xC5, address, code)) + payload
    return body + bytes((sum(body) & 0xFF, 0x5C))


def decode_reply(frame, address, code):
    if code not in REPLY_LENGTHS or len(frame) != REPLY_LENGTHS[code] + 5:
        raise SerialProtocolError("Invalid native response length.")
    if frame[0] != 0xC5 or frame[-1] != 0x5C:
        raise SerialProtocolError("Invalid native frame boundary.")
    if frame[1] != address or frame[2] != code:
        raise SerialProtocolError("Unexpected native response address or function.")
    if sum(frame[:-2]) & 0xFF != frame[-2]:
        raise SerialProtocolError("Invalid native response checksum.")
    if frame[3] != 1:
        raise SerialProtocolError("PD42S1 rejected the command (0x%02X)." % frame[3])
    return frame[4:-2]


def position_payload(delta, rpm, acceleration=0):
    if (isinstance(delta, bool) or not isinstance(delta, int) or abs(delta) > 0x7FFFFFFF or
            isinstance(rpm, bool) or not isinstance(rpm, int) or not 1 <= rpm <= 6000 or
            not isinstance(acceleration, int) or not 0 <= acceleration <= 200):
        raise ValueError("Invalid finite position target.")
    return struct.pack(">BBHI", int(delta < 0), acceleration, rpm, abs(delta))


class NativeSerialBus(object):
    """One port owner and one outstanding request, with priority stop jobs.

    A stop invalidates queued motion and interrupts a running normal job between
    transactions. A single transaction has a bounded timeout and is never replayed.
    """
    def __init__(self, settings, serial_factory=None, timeout=0.15):
        self._axes = [settings[axis] for axis in ("pan", "tilt")]
        self._enabled_bits = {axis["address"]: axis["enabled_feedback"] for axis in self._axes}
        self._limits = {}
        for axis in self._axes:
            if axis["counts_per_turn"] != COUNTS_PER_TURN:
                raise ValueError("Native V1.2 position feedback requires 51200 counts per turn.")
            rpm = int(math.floor(axis["maximum_speed"] * axis["gear_ratio"] / 6.0))
            if not 1 <= rpm <= 6000:
                raise ValueError("Configured output speed/ratio must permit 1..6000 motor RPM.")
            step = int(math.floor(axis["maximum_speed"] * axis["gear_ratio"] *
                                  COUNTS_PER_TURN * STEP_SECONDS / 360.0))
            self._limits[axis["address"]] = (rpm, step)
        if serial_factory is None:
            import serial
            serial_factory = serial.Serial
        self._serial = serial_factory(port=settings["port"], baudrate=settings["baudrate"],
                                      bytesize=8, parity="N", stopbits=1, timeout=0.01,
                                      write_timeout=0.1, xonxoff=False, rtscts=False,
                                      dsrdtr=False, exclusive=True)
        self._timeout = timeout
        self._next_tx = 0.0
        self._baudrate = settings["baudrate"]
        self._queue = queue.PriorityQueue()
        self._lock = threading.Lock()
        self._generation = self._sequence = 0
        self._motion_blocked = True
        self._faulted = False
        self._closed = False
        self._last_probe = 0.0
        self._worker = threading.Thread(target=self._run, name="pd42s1-serial", daemon=True)
        self._worker.start()
        try:
            self._submit(self._probe)
        except Exception:
            self.close()
            raise

    def request_stop(self):
        with self._lock:
            self._generation += 1
            self._motion_blocked = True

    def resume(self):
        with self._lock:
            if self._closed or self._faulted:
                raise SerialProtocolError("Reconnect and calibrate after a serial fault.")
            self._motion_blocked = False

    def _submit(self, operation, priority=1, motion=False):
        future = Future()
        with self._lock:
            if self._closed:
                raise SerialProtocolError("The serial bus is closed.")
            if motion and (self._motion_blocked or self._faulted):
                raise CommandCancelled("Motion is blocked by a stop or serial fault.")
            self._sequence += 1
            self._queue.put((priority, self._sequence, self._generation, motion, operation, future))
        return future.result(timeout=5)

    def _run(self):
        while True:
            priority, _, generation, motion, operation, future = self._queue.get()
            if operation is None:
                return
            try:
                self._check(generation, priority, motion)
                future.set_result(operation((generation, priority, motion)))
            except Exception as exc:
                if not isinstance(exc, CommandCancelled):
                    with self._lock:
                        self._faulted = self._motion_blocked = True
                    # No sequence ID exists on this protocol. Drain late replies
                    # before allowing a different transaction after an error.
                    self._next_tx = time.monotonic() + self._timeout
                future.set_exception(exc)

    def _check(self, generation, priority, motion):
        with self._lock:
            if self._closed or (priority != 0 and generation != self._generation):
                raise CommandCancelled("Operation superseded by stop.")
            if motion and (self._motion_blocked or self._faulted):
                raise CommandCancelled("Motion superseded by stop.")

    def _exchange(self, job, address, code, payload=b""):
        self._check(*job)
        remaining = self._next_tx - time.monotonic()
        if remaining > 0:
            time.sleep(remaining)
        self._check(*job)
        self._serial.reset_input_buffer()
        frame = encode_frame(address, code, payload)
        # One write, never a byte-at-a-time sender or a short-write retry. The
        # adapter must preserve a contiguous UART frame (manual section 4.1).
        if self._serial.write(frame) != len(frame):
            raise SerialProtocolError("Incomplete native command write; command was not replayed.")
        self._next_tx = time.monotonic() + len(frame) * 10.0 / self._baudrate + 0.002
        expected = REPLY_LENGTHS[code] + 5
        reply = bytearray()
        deadline = time.monotonic() + self._timeout
        while time.monotonic() < deadline and len(reply) < expected:
            chunk = self._serial.read(expected - len(reply))
            if chunk:
                reply.extend(chunk)
                if reply[0] != 0xC5:
                    raise SerialProtocolError("Invalid native response header.")
                if len(reply) >= 3 and (reply[1] != address or reply[2] != code):
                    raise SerialProtocolError("Unexpected native response address or function.")
        if len(reply) != expected:
            raise SerialProtocolError("Native response timed out; command was not replayed.")
        return decode_reply(bytes(reply), address, code)

    def _probe(self, job):
        for axis in self._axes:
            address = axis["address"]
            version = self._exchange(job, address, 0x20)
            if not all(version):
                raise SerialProtocolError("Invalid PD42S1 version feedback.")
            config = self._exchange(job, address, 0x32)
            if config[0] != 0 or config[1] != 0 or struct.unpack(">I", config[2:6])[0] != self._baudrate:
                raise SerialProtocolError("Set native position mode, replies and 115200 baud on the driver first.")
            home = self._exchange(job, address, 0x94)
            if home[0] != 0 or home[1] not in (0, 2):
                raise SerialProtocolError("Disable automatic hardware homing and finish homing before use.")
            self._read_axis(job, address)
        self._last_probe = time.monotonic()

    def _read_axis(self, job, address):
        counts = struct.unpack(">i", self._exchange(job, address, 0x2A))[0]
        state = self._exchange(job, address, 0x2C)[0]
        enabled = self._exchange(job, address, 0x2F)[0]
        arrived = self._exchange(job, address, 0x30)[0]
        # V1.2 XLSX and manual disagree on this bit. Require an explicitly
        # verified value for the installed firmware, never guess the polarity.
        if enabled != self._enabled_bits[address] or state not in (0, 1, 2) or arrived not in (0, 1):
            raise SerialProtocolError("Axis disabled, overloaded, stalled, undervoltage or invalid feedback.")
        return {"address": address, "counts": counts, "moving": state == 2 or arrived == 0}

    def read_axes(self):
        def read(job):
            if time.monotonic() - self._last_probe >= 1:
                self._probe(job)
            return [self._read_axis(job, axis["address"]) for axis in self._axes]
        return self._submit(read)

    def move_finite(self, address, counts, counts_per_second):
        def move(job):
            maximum_rpm, maximum_step = self._limits[address]
            current = struct.unpack(">i", self._exchange(job, address, 0x2A))[0]
            delta = counts - current
            if abs(delta) > maximum_step + 1:
                raise SerialProtocolError("Finite target exceeds the configured movement bound.")
            rpm = max(1, int(math.floor(counts_per_second * 60.0 / COUNTS_PER_TURN)))
            if rpm > maximum_rpm:
                raise SerialProtocolError("Finite target exceeds the configured speed limit.")
            # Relative targets avoid ambiguous signed absolute-direction
            # semantics. Recompute once from fresh feedback, and never replay.
            self._exchange(job, address, 0xF3, position_payload(delta, rpm))
        return self._submit(move, priority=2, motion=True)

    def stop_hold(self, address):
        self.request_stop()

        def stop(job):
            # Zero displacement replaces the old target at the current position.
            # Keep position-loop holding torque; FC heats, FA would release tilt.
            self._exchange(job, address, 0xF3, position_payload(0, 1))
            deadline = time.monotonic() + 0.5
            previous = None
            while time.monotonic() < deadline:
                state = self._read_axis(job, address)
                if not state["moving"] and previous == state["counts"]:
                    return
                previous = state["counts"] if not state["moving"] else None
                time.sleep(0.02)
            raise SerialProtocolError("Zero-displacement hold was not confirmed stationary.")
        return self._submit(stop, priority=0)

    def close(self):
        with self._lock:
            if self._closed:
                return
            self._closed = self._motion_blocked = True
            self._generation += 1
            self._sequence += 1
            # Let queued callers observe cancellation instead of stranding them.
            self._queue.put((3, self._sequence, self._generation, False, None, None))
        self._worker.join(timeout=1)
        self._serial.close()
