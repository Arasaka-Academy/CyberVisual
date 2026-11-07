"""Feedback supervision fixtures; native frames have separate serial tests."""
import copy

import pytest

from cybervisual.network_camera.pd42s1 import DEFAULT_PD42S1, PD42S1Driver, validate_pd42s1
from cybervisual.network_camera.ptz import PTZController, PTZUnavailable


class FeedbackBus:
    def __init__(self):
        self.counts = [1000, -2000]
        self.moving = False
        self.moves = []
        self.stops = []
        self.closed = False
        self.fail_move = False

    def read_axes(self):
        return [{"address": i + 1, "counts": value, "moving": self.moving} for i, value in enumerate(self.counts)]

    def move_finite(self, address, counts, speed):
        self.moves.append((address, counts, speed))
        if self.fail_move:
            raise IOError("Serial disconnected after write")
        self.counts[address - 1] = counts

    def stop_hold(self, address):
        self.stops.append(address)

    def close(self):
        self.closed = True


def driver():
    settings = copy.deepcopy(DEFAULT_PD42S1)
    settings["port"] = "/dev/serial/by-id/test-fixture"
    for axis in ("pan", "tilt"):
        settings[axis].update(counts_per_turn=3600, gear_ratio=2,
                              minimum_degrees=-45, maximum_degrees=90, maximum_speed=10,
                              enabled_feedback=1)
    settings["tilt"]["direction"] = -1
    now = [0.0]
    bus = FeedbackBus()
    return PD42S1Driver(settings, bus=bus, clock=lambda: now[0], start_worker=False), bus, now


def test_unconfigured_driver_never_opens_serial_or_allows_calibration():
    motor = PD42S1Driver(DEFAULT_PD42S1)
    assert motor.readiness()["fault"] == "serial_port_unconfigured"
    assert motor.readiness()["calibration_required"]
    with pytest.raises(PTZUnavailable):
        motor.calibrate_center()
    with pytest.raises(PTZUnavailable):
        motor.absolute_move(0.1, 0.1)
    motor.close()


def test_requires_manual_center_and_maps_direction_ratio_and_asymmetric_limits():
    motor, bus, _ = driver()
    controller = PTZController(motor)
    with pytest.raises(PTZUnavailable):
        controller.home()
    with pytest.raises(PTZUnavailable):
        controller.set_preset("unsafe")
    controller.calibrate_center()
    assert controller.status()["pan"] == 0
    controller.absolute_move(1, -1)
    motor._step()
    assert bus.counts == [1040, -1960]  # only two degrees per bounded step
    assert controller.status()["pan"] == pytest.approx(2 / 90)
    assert controller.status()["tilt"] == pytest.approx(-2 / 45)
    for _ in range(100):
        motor._step()
    assert controller.status()["pan"] == pytest.approx(1)
    assert controller.status()["tilt"] == pytest.approx(-1)
    assert all(speed == 200 for _, _, speed in bus.moves)


def test_lease_expiry_and_stop_prevent_queued_movement_without_releasing_torque():
    motor, bus, now = driver()
    motor.calibrate_center()
    motor.continuous_move(1, 0, 2)
    motor._step()
    sent = len(bus.moves)
    now[0] = 2.01
    motor._step()
    assert bus.stops[-2:] == [1, 2]
    motor._step()
    assert len(bus.moves) == sent
    motor.absolute_move(1, 1)
    motor.stop()
    motor._step()
    assert len(bus.moves) == sent
    motor.close()
    assert bus.closed


def test_stop_unconfirmed_invalidates_reference_and_clears_presets_after_recalibration():
    motor, bus, _ = driver()
    controller = PTZController(motor)
    controller.calibrate_center()
    controller.set_preset("origin")
    assert len(controller.presets()) == 1
    controller.calibrate_center()
    assert controller.presets() == []
    bus.moving = True
    with pytest.raises(PTZUnavailable):
        motor.stop()
    assert motor.readiness()["fault"] == "stop_unconfirmed"
    assert motor.readiness()["calibration_required"]
    with pytest.raises(PTZUnavailable):
        motor.absolute_move(0, 0)


def test_failed_motion_acknowledgement_is_not_replayed():
    motor, bus, _ = driver()
    motor.calibrate_center()
    bus.fail_move = True
    motor.absolute_move(1, 1)
    with pytest.raises(PTZUnavailable):
        motor._step()
    assert len(bus.moves) == 1
    motor._step()
    assert len(bus.moves) == 1
    assert motor.readiness()["calibration_required"]


def test_stop_attempts_both_axes_when_first_axis_is_unreachable():
    motor, bus, _ = driver()
    motor.calibrate_center()
    bus.stops = []
    def stop(address):
        bus.stops.append(address)
        if address == 1:
            raise IOError("Axis missing")
    bus.stop_hold = stop
    with pytest.raises(PTZUnavailable):
        motor.stop()
    assert bus.stops == [1, 2]
    assert motor.readiness()["fault"] == "stop_unconfirmed"


def test_unexpected_displacement_invalidates_reference_before_another_move():
    motor, bus, _ = driver()
    motor.calibrate_center()
    bus.counts[0] = 0  # controller reset or external movement
    motor.absolute_move(1, 0)
    with pytest.raises(PTZUnavailable):
        motor._step()
    assert not bus.moves
    assert motor.readiness()["calibration_required"]


def test_target_not_reached_does_not_accumulate_relative_commands():
    motor, bus, now = driver()
    motor.calibrate_center()
    def lost_target(address, counts, speed):
        bus.moves.append((address, counts, speed))
    bus.move_finite = lost_target
    motor.absolute_move(1, 0)
    motor._step()
    for _ in range(10):
        motor._step()
    assert len(bus.moves) == 1
    now[0] = 1.6
    with pytest.raises(PTZUnavailable):
        motor._step()
    assert motor.readiness()["fault"] == "finite_target_unconfirmed"


@pytest.mark.parametrize("index,center", [
    (0, 0x7FFFFFFF - 1799), (0, -0x80000000 + 899),
    (1, 0x7FFFFFFF - 899), (1, -0x80000000 + 1799),
])
def test_calibration_rejects_travel_beyond_signed_feedback(index, center):
    motor, bus, _ = driver()
    bus.counts[index] = center
    with pytest.raises(PTZUnavailable, match="signed native position feedback"):
        motor.calibrate_center()
    assert motor.readiness()["fault"] == "configuration_required"
    assert motor.readiness()["calibration_required"]
    assert not bus.moves
    with pytest.raises(PTZUnavailable):
        motor.absolute_move(0, 0)
    motor.close()


def test_calibration_accepts_travel_ending_at_signed_feedback_boundaries():
    motor, bus, _ = driver()
    bus.counts = [0x7FFFFFFF - 1800, -0x80000000 + 1800]
    motor.calibrate_center()
    assert motor.readiness()["calibrated"]
    assert motor.status()["position_known"]
    assert not bus.moves
    motor.close()


@pytest.mark.parametrize("patch", [
    {"port": "/dev/../tmp/serial"}, {"baudrate": 9600},
    {"pan": {"address": 2}}, {"pan": {"direction": 0}},
    {"tilt": {"counts_per_turn": float("nan")}},
    {"pan": {"minimum_degrees": 5}},
    {"pan": {"enabled_feedback": True}}, {"tilt": {"enabled_feedback": 2}},
])
def test_rejects_unsafe_mechanical_configuration(patch):
    with pytest.raises(ValueError):
        validate_pd42s1(patch)
