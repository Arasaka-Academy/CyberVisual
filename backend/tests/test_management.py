import xml.etree.ElementTree as ET

import pytest

from cybervisual.app import create_app
from cybervisual.config import DEFAULT_CONFIG, merge_config
from cybervisual.network_camera.ptz import PTZController, PTZUnavailable
from cybervisual.runtime import RuntimeService
from test_onvif import soap_document


@pytest.fixture
def managed_camera(monkeypatch, tmp_path):
    monkeypatch.setenv("CYBERVISUAL_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("CYBERVISUAL_ONVIF_USERNAME", "viewer")
    monkeypatch.setenv("CYBERVISUAL_ONVIF_PASSWORD", "test-password")
    config = merge_config(DEFAULT_CONFIG, {"network_camera": {
        "enabled": True, "ptz_driver": "simulated", "advertise_host": "127.0.0.1"}})
    runtime = RuntimeService(config=config)
    app = create_app(runtime=runtime, auto_start=False)
    return app.test_client(), runtime


def test_disabled_ptz_can_be_read_but_cannot_move(monkeypatch, tmp_path):
    monkeypatch.setenv("CYBERVISUAL_STATE_DIR", str(tmp_path))
    client = create_app(runtime=RuntimeService(), auto_start=False).test_client()
    result = client.get("/api/ptz")
    assert result.status_code == 200
    assert result.get_json()["state"] == "disabled"
    assert result.get_json()["position"] is None
    assert client.post("/api/ptz/command", json={"action": "home"}).status_code == 503


def test_rest_and_onvif_share_position_and_persistent_presets(managed_camera):
    client, runtime = managed_camera
    assert client.post("/api/ptz/command", json={"action": "absolute_move", "pan": .4, "tilt": -.3}).status_code == 200
    preset = client.post("/api/ptz/command", json={"action": "set_preset", "name": "门口"}).get_json()["presets"][0]
    namespace = "http://www.onvif.org/ver20/ptz/wsdl"
    result = client.post("/onvif/ptz_service", data=soap_document(namespace, "GetStatus", children="<op:ProfileToken>raw</op:ProfileToken>"))
    assert result.status_code == 200
    position = ET.fromstring(result.data).find(".//{http://www.onvif.org/ver10/schema}PanTilt")
    assert float(position.get("x")) == pytest.approx(.4)
    assert client.post("/api/ptz/command", json={"action": "home"}).get_json()["position"]["pan"] == 0
    result = client.post("/api/ptz/command", json={"action": "goto_preset", "token": preset["token"]})
    assert result.get_json()["position"]["tilt"] == pytest.approx(-.3)
    runtime.network_camera._ptz = None
    assert client.get("/api/ptz").get_json()["presets"][0]["token"] == preset["token"]
    assert client.post("/api/ptz/command", json={"action": "remove_preset", "token": preset["token"]}).get_json()["presets"] == []


@pytest.mark.parametrize("payload", [
    [], {"action": "unknown"}, {"action": "stop", "pan": 1},
    {"action": "absolute_move", "pan": True, "tilt": 0},
    {"action": "relative_move", "pan": 2, "tilt": 0},
    {"action": "relative_move", "pan": 10 ** 500, "tilt": 0},
    {"action": "continuous_move", "pan": "1", "tilt": 0},
    {"action": "continuous_move", "pan": 1, "tilt": 0, "timeout": 30},
    {"action": "goto_preset", "token": 123}, {"action": "set_preset", "name": ""},
])
def test_ptz_command_rejects_bad_json_arguments(managed_camera, payload):
    client, _ = managed_camera
    result = client.post("/api/ptz/command", json=payload)
    assert result.status_code == 400
    assert "error" in result.get_json()


def test_ptz_requires_json_and_has_two_second_watchdog(managed_camera):
    client, runtime = managed_camera
    assert client.post("/api/ptz/command", data='{"action":"home"}', content_type="text/plain").status_code == 400
    controller = runtime.network_camera.ptz
    now = [10.0]
    controller.driver._clock = lambda: now[0]
    controller.driver._updated = 10.0
    controller.driver._deadline = 10.0
    result = client.post("/api/ptz/command", json={"action": "continuous_move", "pan": .2, "tilt": 0})
    assert result.get_json()["position"]["moving"]
    now[0] += 3
    assert client.get("/api/ptz").get_json()["position"]["pan"] == pytest.approx(.4)
    assert not client.get("/api/ptz").get_json()["position"]["moving"]
    assert client.post("/api/ptz/command", json={"action": "stop"}).status_code == 200


def test_driver_fault_is_readable_without_disclosing_internal_error(managed_camera):
    client, runtime = managed_camera
    class BrokenDriver:
        def status(self):
            raise PTZUnavailable("private transport details")
        def stop(self):
            raise PTZUnavailable("private transport details")
    runtime.network_camera._ptz = PTZController(BrokenDriver())
    result = client.get("/api/ptz")
    assert result.status_code == 200
    assert result.get_json()["state"] == "unavailable"
    assert "private" not in result.get_data(as_text=True)
    assert client.post("/api/ptz/command", json={"action": "stop"}).status_code == 503


@pytest.mark.parametrize("payload", [None, {}, {"confirm": False}, {"confirm": 1},
                                     {"confirm": True, "pan": 0}])
def test_center_calibration_requires_exact_explicit_confirmation(managed_camera, payload):
    client, _ = managed_camera
    assert client.post("/api/ptz/calibrate-center", json=payload).status_code == 400


def test_center_api_shares_hardware_reference_with_onvif_and_reports_new_fault(managed_camera):
    from test_pd42s1 import driver
    client, runtime = managed_camera
    motor, bus, _ = driver()
    runtime.network_camera.settings["ptz_driver"] = "pd42s1"
    runtime.network_camera._ptz = PTZController(motor)
    before = client.get("/api/ptz").get_json()
    assert before["hardware_ready"] and before["calibration_required"]
    assert before["position"] is None
    assert client.post("/api/ptz/command", json={"action": "home"}).status_code == 503
    calibrated = client.post("/api/ptz/calibrate-center", json={"confirm": True}).get_json()
    assert calibrated["calibrated"] and not calibrated["calibration_required"]
    assert calibrated["position"]["pan"] == 0
    namespace = "http://www.onvif.org/ver20/ptz/wsdl"
    result = client.post("/onvif/ptz_service", data=soap_document(
        namespace, "AbsoluteMove", children='<op:ProfileToken>raw</op:ProfileToken>'
        '<op:Position><tt:PanTilt xmlns:tt="http://www.onvif.org/ver10/schema" x="0.4" y="-0.3"/></op:Position>'))
    assert result.status_code == 200
    motor._step()
    assert client.get("/api/ptz").get_json()["position"]["pan"] > 0
    bus.counts[0] += 100000
    fault = client.get("/api/ptz").get_json()
    assert fault["state"] == "unavailable"
    assert fault["fault"] == "position_outside_limits"
    assert fault["calibration_required"] and fault["position"] is None
    motor.close()


def test_unconfigured_pd42s1_keeps_video_management_available_and_rejects_calibration(managed_camera):
    from cybervisual.network_camera.pd42s1 import PD42S1Driver, DEFAULT_PD42S1
    client, runtime = managed_camera
    runtime.network_camera.settings["ptz_driver"] = "pd42s1"
    runtime.network_camera._ptz = PTZController(PD42S1Driver(DEFAULT_PD42S1))
    state = client.get("/api/ptz").get_json()
    assert not state["hardware_ready"] and state["fault"] == "serial_port_unconfigured"
    assert client.post("/api/ptz/calibrate-center", json={"confirm": True}).status_code == 503
    assert client.get("/api/events/recent").status_code == 200


def test_recent_events_work_without_onvif_and_survive_subscription_close(monkeypatch, tmp_path):
    monkeypatch.setenv("CYBERVISUAL_STATE_DIR", str(tmp_path))
    runtime = RuntimeService()
    client = create_app(runtime=runtime, auto_start=False).test_client()
    runtime.events.observe([{"label": "person", "confidence": .9}], frame_ts=100, now=1)
    runtime.events.offline("Camera unavailable")
    runtime.events.close()
    result = client.get("/api/events/recent").get_json()
    assert result["capacity"] == 200
    assert not result["status"]["online"]
    assert result["status"]["presence"]["person"]
    assert [e["state"] for e in result["events"]] == [True, True, False]
    assert len({e["id"] for e in result["events"]}) == 3
    assert client.get("/api/events/recent").get_json()["events"] == result["events"]
