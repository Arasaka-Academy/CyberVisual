"""Native frames from the official V1.2 sources plus a fragmented UART fixture.

This verifies the wire implementation, not physical motors, holding or timing.
"""
import copy
import os
import select
import struct
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from cybervisual.network_camera.pd42s1 import DEFAULT_PD42S1, PD42S1Driver
from cybervisual.network_camera.pd42s1_serial import (
    CommandCancelled, NativeSerialBus, SerialProtocolError,
    decode_reply, encode_frame, position_payload,
)


def settings():
    result = copy.deepcopy(DEFAULT_PD42S1)
    result["port"] = "/dev/serial/by-id/fixture"
    for name in ("pan", "tilt"):
        result[name].update(gear_ratio=2, minimum_degrees=-45, maximum_degrees=90,
                            maximum_speed=10, enabled_feedback=1)
    return result


def reply(address, code, data=b"", result=1):
    body = bytes((0xC5, address, code, result)) + data
    return body + bytes((sum(body) & 0xFF, 0x5C))


class UARTFixture:
    def __init__(self, **kwargs):
        self.options = kwargs
        self.sent = []
        self.positions = {1: 1000, 2: -2000}
        self.response = b""
        self.fragment = 1
        self.corrupt = None
        self.closed = False
        self.moving = False
        self.enabled = 1
        self.mode = 0
        self.auto_home = 0
        self.gate = None
        self.started = threading.Event()

    def reset_input_buffer(self):
        self.response = b""

    def write(self, frame):
        self.sent.append((time.monotonic(), frame))
        address, code = frame[1:3]
        assert sum(frame[:-2]) & 0xFF == frame[-2] and frame[-1] == 0x5C
        if code == 0x20:
            data = b"\x0c\x0a"
        elif code == 0x32:
            data = bytes((self.mode, 0)) + struct.pack(">I", 115200) + bytes(38)
        elif code == 0x94:
            data = bytes((self.auto_home, 0)) + bytes(15)
        elif code == 0x2A:
            data = struct.pack(">i", self.positions[address])
        elif code == 0x2C:
            data = bytes((2 if self.moving else 1,))
        elif code == 0x2F:
            data = bytes((self.enabled,))
        elif code == 0x30:
            data = bytes((0 if self.moving else 1,))
        elif code == 0xF3:
            direction, acceleration, rpm, delta = struct.unpack(">BBHI", frame[3:-2])
            self.positions[address] += delta * (-1 if direction else 1)
            if delta:
                self.started.set()
            data = b""
        else:
            raise AssertionError("Unexpected parameter or motion command")
        self.response = reply(address, code, data)
        if self.corrupt:
            self.response = self.corrupt(self.response)
        return len(frame)

    def read(self, size):
        if self.gate is not None and self.started.is_set() and not self.gate.is_set():
            time.sleep(0.002)
            return b""
        out = self.response[:min(size, self.fragment)]
        self.response = self.response[len(out):]
        if not out:
            time.sleep(0.002)
        return out

    def close(self):
        self.closed = True


def bus_with_fixture():
    uart = UARTFixture()
    bus = NativeSerialBus(settings(), serial_factory=lambda **opts: uart, timeout=0.08)
    return bus, uart


def test_official_manual_golden_frames():
    # Manual printed pages 34, 35 and 53; PDF pages 40, 41 and 59.
    assert encode_frame(1, 0x2A) == bytes.fromhex("C5 01 2A F0 5C")
    assert decode_reply(bytes.fromhex("C5 01 2A 01 00 07 D0 00 C8 5C"), 1, 0x2A) == struct.pack(">i", 512000)
    assert encode_frame(1, 0x2C) == bytes.fromhex("C5 01 2C F2 5C")
    assert decode_reply(bytes.fromhex("C5 01 2C 01 01 F4 5C"), 1, 0x2C) == b"\x01"
    assert encode_frame(1, 0xF3, position_payload(512000, 2000, 100)) == bytes.fromhex(
        "C5 01 F3 00 64 07 D0 00 07 D0 00 CB 5C")
    assert decode_reply(bytes.fromhex("C5 01 F3 01 BA 5C"), 1, 0xF3) == b""


@pytest.mark.parametrize("frame", [
    "C5 02 2A 01 00 07 D0 00 C9 5C",  # wrong address, valid checksum
    "C5 01 2A 01 00 07 D0 00 C9 5C",  # checksum
    "C5 01 2A 01 00 07 D0 C8 5C",     # length
    "C5 01 2A 01 00 07 D0 00 C8 00",  # tail
    "C5 01 2C 01 01 F4 5C",           # function and length
    "C5 01 F3 E6 9F 5C",             # device rejected payload
])
def test_rejects_invalid_response(frame):
    with pytest.raises(SerialProtocolError):
        decode_reply(bytes.fromhex(frame), 1, 0xF3 if "F3" in frame else 0x2A)


@pytest.mark.parametrize("code", [0x01, 0x02, 0x04, 0x60, 0x62, 0xF1, 0xF8, 0xFA, 0xFB, 0xFC])
def test_does_not_expose_parameter_writes_unbounded_motion_brake_or_disable(code):
    with pytest.raises(ValueError):
        encode_frame(1, code)


def test_fragmented_dual_axis_feedback_and_finite_target_keep_torque():
    bus, uart = bus_with_fixture()
    try:
        feedback = bus.read_axes()
        assert [item["counts"] for item in feedback] == [1000, -2000]
        assert not any(item["moving"] for item in feedback)
        bus.resume()
        bus.move_finite(2, -2050, 2800)
        bus.stop_hold(1)
        bus.stop_hold(2)
        assert uart.positions[2] == -2050
        commands = [frame for _, frame in uart.sent if frame[2] == 0xF3]
        assert len(commands) == 3
        assert struct.unpack(">BBHI", commands[0][3:-2]) == (1, 0, 3, 50)
        assert all(struct.unpack(">BBHI", frame[3:-2]) == (0, 0, 1, 0) for frame in commands[1:])
        # Every command is issued once, and the required interframe gap is kept.
        assert all(after[0] - before[0] >= 0.002 for before, after in zip(uart.sent, uart.sent[1:]))
        with pytest.raises(CommandCancelled):
            bus.move_finite(1, 1010, 2800)
    finally:
        bus.close()
    assert uart.closed


@pytest.mark.parametrize("damage", [
    lambda frame: bytes((frame[0], 2 if frame[1] == 1 else 1)) + frame[2:],
    lambda frame: frame[:-2] + bytes((frame[-2] ^ 1, frame[-1])),
    lambda frame: frame[:-1],
    lambda frame: b"",
])
def test_bad_or_missing_motion_reply_is_never_replayed(damage):
    bus, uart = bus_with_fixture()
    try:
        bus.resume()
        uart.corrupt = lambda frame: damage(frame) if frame[2] == 0xF3 else frame
        with pytest.raises(SerialProtocolError):
            bus.move_finite(1, 1050, 2800)
        with pytest.raises(CommandCancelled):
            bus.move_finite(1, 1050, 2800)
        assert sum(frame[2] == 0xF3 for _, frame in uart.sent) == 1
    finally:
        bus.close()


def test_stop_preempts_queued_motion_after_one_outstanding_transaction():
    bus, uart = bus_with_fixture()
    gate = uart.gate = threading.Event()
    try:
        bus.resume()
        with ThreadPoolExecutor(max_workers=3) as pool:
            first = pool.submit(bus.move_finite, 1, 1050, 2800)
            assert uart.started.wait(1)
            second = pool.submit(bus.move_finite, 2, -2050, 2800)
            limit = time.monotonic() + 1
            while bus._queue.qsize() < 1 and time.monotonic() < limit:
                time.sleep(0.001)
            stop = pool.submit(bus.stop_hold, 1)
            limit = time.monotonic() + 1
            while bus._queue.qsize() < 2 and time.monotonic() < limit:
                time.sleep(0.001)
            gate.set()
            first.result(timeout=2)
            stop.result(timeout=2)
            with pytest.raises(CommandCancelled):
                second.result(timeout=2)
        motion = [frame for _, frame in uart.sent if frame[2] == 0xF3]
        assert len(motion) == 2 and all(frame[1] == 1 for frame in motion)
        assert int.from_bytes(motion[-1][7:11], "big") == 0
    finally:
        gate.set()
        bus.close()


def test_native_bus_enforces_short_distance_and_speed_bounds():
    for target, speed in ((100000, 2800), (1010, 1000000)):
        bus, uart = bus_with_fixture()
        try:
            bus.resume()
            with pytest.raises(SerialProtocolError):
                bus.move_finite(1, target, speed)
            assert not any(frame[2] == 0xF3 for _, frame in uart.sent)
        finally:
            bus.close()


def test_partial_write_does_not_retry_the_motion():
    bus, uart = bus_with_fixture()
    original = uart.write
    def short_write(frame):
        length = original(frame)
        return length - 1 if frame[2] == 0xF3 else length
    uart.write = short_write
    try:
        bus.resume()
        with pytest.raises(SerialProtocolError, match="not replayed"):
            bus.move_finite(1, 1050, 2800)
        assert sum(frame[2] == 0xF3 for _, frame in uart.sent) == 1
    finally:
        bus.close()


def test_stop_requires_stationary_feedback_and_accepts_explicit_zero_enabled_bit():
    config = settings()
    for axis in ("pan", "tilt"):
        config[axis]["enabled_feedback"] = 0
    uart = UARTFixture()
    uart.enabled = 0
    bus = NativeSerialBus(config, serial_factory=lambda **opts: uart)
    try:
        uart.moving = True
        with pytest.raises(SerialProtocolError, match="not confirmed stationary"):
            bus.stop_hold(1)
    finally:
        bus.close()


@pytest.mark.parametrize("field,value", [("mode", 1), ("auto_home", 1), ("enabled", 0)])
def test_probe_rejects_unsafe_hardware_settings_without_rewriting_them(field, value):
    uart = UARTFixture()
    setattr(uart, field, value)
    with pytest.raises(SerialProtocolError):
        NativeSerialBus(settings(), serial_factory=lambda **opts: uart)
    assert uart.closed
    assert all(frame[2] in (0x20, 0x32, 0x94, 0x2A, 0x2C, 0x2F, 0x30) for _, frame in uart.sent)


def test_manual_recalibration_can_reopen_after_a_serial_fault(monkeypatch):
    import cybervisual.network_camera.pd42s1 as module
    fixtures = []
    def open_bus(config):
        uart = UARTFixture()
        fixtures.append(uart)
        return NativeSerialBus(config, serial_factory=lambda **opts: uart)
    monkeypatch.setattr(module, "NativeSerialBus", open_bus)
    driver = PD42S1Driver(settings(), start_worker=False)
    try:
        assert driver.readiness()["calibration_required"]
        driver.calibrate_center()
        fixtures[0].corrupt = lambda frame: b""
        with pytest.raises(Exception):
            driver.status()
        assert driver.readiness()["calibration_required"]
        driver.calibrate_center()
        assert len(fixtures) == 2 and fixtures[0].closed
        assert driver.readiness()["calibrated"]
        assert not any(int.from_bytes(frame[7:11], "big") for uart in fixtures for _, frame in uart.sent if frame[2] == 0xF3)
    finally:
        driver.close()


def test_pyserial_posix_port_with_fragmented_motor_responder():
    """Exercise real pyserial and kernel TTY I/O; no motor is connected."""
    import pty
    import serial
    master, slave = pty.openpty()
    done = threading.Event()
    uart = UARTFixture()
    errors = []

    def respond():
        pending = bytearray()
        try:
            while not done.is_set():
                if not select.select([master], [], [], 0.05)[0]:
                    continue
                pending.extend(os.read(master, 1024))
                while len(pending) >= 3:
                    length = 13 if pending[2] == 0xF3 else 5
                    if len(pending) < length:
                        break
                    frame = bytes(pending[:length])
                    del pending[:length]
                    uart.write(frame)
                    # Deliberately split the response across reads.
                    for i in range(0, len(uart.response), 2):
                        os.write(master, uart.response[i:i + 2])
                        time.sleep(0.001)
        except Exception as exc:
            if not done.is_set():
                errors.append(exc)

    worker = threading.Thread(target=respond, daemon=True)
    worker.start()
    bus = None
    try:
        config = settings()
        config["port"] = os.ttyname(slave)
        bus = NativeSerialBus(config)
        assert bus._serial.baudrate == 115200 and bus._serial.bytesize == serial.EIGHTBITS
        assert bus._serial.parity == serial.PARITY_NONE and bus._serial.stopbits == serial.STOPBITS_ONE
        assert bus.read_axes()[1]["counts"] == -2000
        bus.resume()
        bus.move_finite(1, 1050, 2800)
        bus.stop_hold(1)
        assert bus.read_axes()[0]["counts"] == 1050
        assert not errors
    finally:
        if bus:
            bus.close()
        done.set()
        worker.join(timeout=1)
        os.close(master)
        os.close(slave)
