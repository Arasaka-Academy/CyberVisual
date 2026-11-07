import pytest

from cybervisual.network_camera.ptz import PTZController, PTZError, SimulatedPTZDriver


def test_disabled_driver_rejects_commands():
    controller = PTZController()
    assert controller.enabled is False
    with pytest.raises(PTZError):
        controller.absolute_move(0.1, 0.2)


def test_moves_validate_limits_and_stop_at_timeout():
    now = [10.0]
    controller = PTZController(SimulatedPTZDriver(clock=lambda: now[0]))
    controller.absolute_move(0.2, -0.3)
    controller.relative_move(0.1, 0.1)
    assert controller.status()["pan"] == pytest.approx(0.3)
    assert controller.status()["tilt"] == pytest.approx(-0.2)
    with pytest.raises(PTZError):
        controller.absolute_move(1.1, 0)
    with pytest.raises(PTZError):
        controller.continuous_move(0.1, 0, timeout=2.01)
    controller.continuous_move(0.1, 0, timeout=2)
    now[0] += 3
    assert controller.status()["pan"] == pytest.approx(0.5)
    assert controller.status()["moving"] is False
    now[0] += 5
    assert controller.status()["pan"] == pytest.approx(0.5)


def test_simulated_driver_exposes_capabilities_and_clamps_continuous_limits():
    now = [0.0]
    controller = PTZController(SimulatedPTZDriver(clock=lambda: now[0]))
    assert controller.capabilities()["absolute_move"] is True
    assert controller.capabilities()["zoom"] is False
    controller.absolute_move(0.9, -0.9)
    controller.continuous_move(1, -1)
    now[0] = 1.0
    assert controller.status()["pan"] == 1
    assert controller.status()["tilt"] == -1
    assert not controller.status()["moving"]


def test_stop_home_and_persistent_presets(tmp_path):
    now = [0.0]
    state_path = str(tmp_path / "presets.json")
    controller = PTZController(SimulatedPTZDriver(clock=lambda: now[0]), state_path=state_path)
    controller.absolute_move(0.5, -0.5)
    token = controller.set_preset("Door")
    controller.home()
    assert controller.status()["pan"] == 0
    controller.goto_preset(token)
    assert controller.status()["tilt"] == -0.5
    controller.continuous_move(1, 0)
    now[0] = 0.1
    controller.stop()
    now[0] = 10
    assert controller.status()["pan"] == pytest.approx(0.6)
    restored = PTZController(SimulatedPTZDriver(), state_path=state_path)
    restored.goto_preset(token)
    assert restored.status()["pan"] == 0.5
