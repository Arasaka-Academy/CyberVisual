"""Real ONVIF client and media decoder checks; run in the supplied Linux image."""
import concurrent.futures
import json
import os
import socket
import subprocess
import threading
import time
from pathlib import Path
from urllib.parse import urlparse

import pytest
import requests
import numpy as np
from requests.auth import HTTPDigestAuth
from werkzeug.serving import make_server

if os.environ.get("RUN_CAMERA_INTEROP") != "1":
    pytest.skip("Set RUN_CAMERA_INTEROP=1 in the Linux GStreamer test image.", allow_module_level=True)

from onvif import ONVIFCamera
from onvif.client import ONVIFService
from zeep.transports import Transport
from zeep import Client, Settings
from zeep.wsse.username import UsernameToken
from zeep.plugins import HistoryPlugin

from cybervisual.app import create_app
from cybervisual.config import DEFAULT_CONFIG, merge_config
from cybervisual.runtime import RuntimeService


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture
def camera(monkeypatch, tmp_path):
    http_port, rtsp_port = free_port(), free_port()
    monkeypatch.setenv("CYBERVISUAL_ONVIF_USERNAME", "viewer")
    monkeypatch.setenv("CYBERVISUAL_ONVIF_PASSWORD", "test-password")
    monkeypatch.setenv("CYBERVISUAL_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("CYBERVISUAL_PORT", str(http_port))
    config = merge_config(DEFAULT_CONFIG, {
        "source": "synthetic", "detector_backend": "mock", "auto_snapshot_enabled": False,
        "resolution": {"width": 320, "height": 240},
        "network_camera": {"enabled": True, "advertise_host": "127.0.0.1", "encoder": "software",
                           "rtsp_port": rtsp_port, "discovery_enabled": False, "ptz_driver": "simulated"},
    })
    runtime = RuntimeService(config=config)
    app = create_app(runtime=runtime, auto_start=False)
    http = make_server("127.0.0.1", http_port, app, threaded=True)
    worker = threading.Thread(target=http.serve_forever, daemon=True)
    worker.start()
    try:
        runtime.start()
        assert runtime.network_camera.status()["state"] == "running", runtime.network_camera.status()
        session = requests.Session()
        session.trust_env = False
        client = ONVIFCamera("127.0.0.1", http_port, "viewer", "test-password", no_cache=True,
                             adjust_time=True, transport=Transport(session=session, timeout=5, operation_timeout=5))
        yield runtime, client, "http://127.0.0.1:%d" % http_port
    finally:
        runtime.stop()
        assert not runtime._thread.is_alive()
        assert not runtime._capture_thread.is_alive()
        assert not any(t.name.startswith("cybervisual-rtsp") for t in threading.enumerate())
        assert not runtime.events.status()["subscribers"]
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", rtsp_port))
        http.shutdown()
        http.server_close()
        worker.join(timeout=2)


def stream_uri(client, profile):
    media = client.create_media_service()
    return media.GetStreamUri({"ProfileToken": profile, "StreamSetup": {
        "Stream": "RTP-Unicast", "Transport": {"Protocol": "RTSP"}}}).Uri


def authenticated_uri(uri):
    return uri.replace("rtsp://", "rtsp://viewer:test-password@", 1)


def decode(uri, transport, frames=3, width=320, height=240):
    result = subprocess.run([
        "ffmpeg", "-v", "error", "-rtsp_transport", transport, "-i", authenticated_uri(uri),
        "-frames:v", str(frames), "-pix_fmt", "rgb24", "-f", "rawvideo", "pipe:1",
    ], capture_output=True, timeout=20)
    assert result.returncode == 0, result.stderr.decode(errors="replace")
    assert len(result.stdout) == width * height * 3 * frames
    return result.stdout


def test_even_resolution_with_unaligned_rgb_rows_decodes_both_profiles(camera, monkeypatch):
    runtime, client, base = camera
    frame = np.zeros((242, 322, 3), dtype=np.uint8)
    frame[:, :161] = [210, 40, 20]
    frame[:, 161:] = [10, 170, 60]

    class ColorSource:
        def open(self):
            pass

        def read(self):
            return True, frame.copy()

        def close(self):
            pass

    monkeypatch.setattr("cybervisual.runtime.build_frame_source", lambda config: ColorSource())
    response = requests.put(base + "/api/config", json={"resolution": {"width": 322, "height": 242}}, timeout=5)
    assert response.status_code == 200
    for profile in ("raw", "annotated"):
        frames = decode(stream_uri(client, profile), "tcp", width=322, height=242)
        pixels = np.frombuffer(frames, dtype=np.uint8).reshape(3, 242, 322, 3)
        # Stay away from the detector's overlays and color boundaries.
        left = pixels[:, 180:220, 20:60].mean(axis=(0, 1, 2))
        right = pixels[:, 180:220, 260:300].mean(axis=(0, 1, 2))
        assert np.allclose(left, [210, 40, 20], atol=12), left
        assert np.allclose(right, [10, 170, 60], atol=12), right


def test_abandoned_rtsp_session_expires_without_a_teardown(camera):
    runtime, client, base = camera
    rtsp = runtime.network_camera._rtsp
    pool = rtsp._server.get_session_pool()
    process = subprocess.Popen([
        "ffmpeg", "-v", "error", "-rtsp_transport", "udp", "-i", authenticated_uri(stream_uri(client, "raw")),
        "-f", "null", "-",
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and not pool.get_n_sessions():
            time.sleep(0.02)
        assert pool.get_n_sessions() == 1
        from gi.repository import GstRtspServer

        def expire_session(pool, session, data):
            session.set_timeout(1)
            return GstRtspServer.RTSPFilterResult.KEEP

        pool.filter(expire_session, None)
        process.kill()
        process.wait(timeout=5)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and pool.get_n_sessions():
            time.sleep(0.02)
        assert pool.get_n_sessions() == 0
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline and rtsp.status()["streams"]["raw"]["active"]:
            time.sleep(0.02)
        assert not rtsp.status()["streams"]["raw"]["active"]
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=5)


def test_encoder_bus_errors_are_visible_in_output_status(camera, monkeypatch):
    from cybervisual.network_camera.rtsp import RTSPServer

    original_pipeline = RTSPServer._pipeline

    def failing_pipeline(server, profile):
        pipeline = original_pipeline(server, profile)
        return pipeline.replace("! videoconvert", "! identity error-after=2 ! videoconvert") if profile == "raw" else pipeline

    runtime, client, base = camera
    monkeypatch.setattr(RTSPServer, "_pipeline", failing_pipeline)
    runtime.update_config({"network_camera": {"raw_bitrate_kbps": 1500}})
    process = subprocess.Popen([
        "ffmpeg", "-v", "error", "-rtsp_transport", "tcp", "-i", authenticated_uri(stream_uri(client, "raw")),
        "-frames:v", "3", "-f", "null", "-",
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and not runtime.network_camera.status()["profiles"][0].get("last_error"):
            time.sleep(0.02)
        assert runtime.network_camera.status()["profiles"][0]["last_error"]
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=5)
    decode(stream_uri(client, "annotated"), "tcp")


@pytest.mark.parametrize("transport", ["tcp", "udp"])
def test_onvif_profiles_lead_to_decodable_h264_streams(camera, transport):
    runtime, client, base = camera
    services = client.devicemgmt.GetServices({"IncludeCapability": True})
    assert len(services) == 5
    profiles = client.create_media_service().GetProfiles()
    assert [profile.token for profile in profiles] == ["raw", "annotated"]
    assert profiles[0].VideoEncoderConfiguration.Encoding == "H264"
    assert profiles[0].VideoSourceConfiguration.SourceToken == profiles[1].VideoSourceConfiguration.SourceToken
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(decode, stream_uri(client, profile), transport) for profile in ("raw", "annotated")]
        original, annotated = [future.result() for future in futures]
    original_frames = np.frombuffer(original, dtype=np.uint8).reshape(3, 240, 320, 3)
    annotated_frames = np.frombuffer(annotated, dtype=np.uint8).reshape(3, 240, 320, 3)
    # The person's left border is outside the animated synthetic rectangle.
    # Its green overlay must survive H.264; raw frames must lack that border.
    raw_border = original_frames[:, 55:175, 44:47].mean(axis=(0, 1, 2))
    annotated_border = annotated_frames[:, 55:175, 44:47].mean(axis=(0, 1, 2))
    assert annotated_border[2] > 145
    assert annotated_border[2] - raw_border[2] > 60
    # A fresh session after all clients disconnect must also decode.
    decode(stream_uri(client, "raw"), transport)
    media = client.create_media_service()
    for profile in ("raw", "annotated"):
        uri = media.GetSnapshotUri({"ProfileToken": profile}).Uri
        assert requests.get(uri, timeout=5).status_code == 401
        response = requests.get(uri, auth=HTTPDigestAuth("viewer", "test-password"), timeout=5)
        assert response.status_code == 200
        assert response.headers["Content-Type"].startswith("image/jpeg")
        assert response.content.startswith(b"\xff\xd8")


def make_event_service(client, address, binding):
    service = ONVIFService(address, "viewer", "test-password", str(Path(client.wsdl_dir) / "events.wsdl"),
                           no_cache=True, binding_name="{http://www.onvif.org/ver10/events/wsdl}" + binding)
    service.history = HistoryPlugin()
    service.zeep_client.plugins.append(service.history)
    return service


def states(result, topic_suffix):
    found = []
    for event in result.NotificationMessage:
        # Zeep drops mixed text in wsnt:TopicExpressionType. The application
        # payload retains the category; topic XML is checked separately below.
        payload = event.Message._value_1
        if isinstance(payload, list):
            payload = payload[0]
        category = payload.find(".//{http://www.onvif.org/ver10/schema}SimpleItem[@Name='Category']").get("Value")
        expected = {"PersonPresence": "person", "VehiclePresence": "vehicle", "AnalyticsOnline": "analytics"}[topic_suffix]
        if category != expected:
            continue
        found.append(payload.find(".//{http://www.onvif.org/ver10/schema}SimpleItem[@Name='State']").get("Value"))
    return found


def test_independent_client_receives_ai_edges_and_manages_subscription(camera):
    runtime, client, base = camera
    events = client.create_events_service()
    assert events.GetEventProperties().FixedTopicSet is True
    reference = events.CreatePullPointSubscription({"InitialTerminationTime": "PT60S"})
    address = reference.SubscriptionReference.Address._value_1
    pull = make_event_service(client, address, "PullPointSubscriptionBinding")
    manager = make_event_service(client, address, "SubscriptionManagerBinding")
    other_reference = events.CreatePullPointSubscription({"InitialTerminationTime": "PT60S"})
    other_address = other_reference.SubscriptionReference.Address._value_1
    other = make_event_service(client, other_address, "PullPointSubscriptionBinding")
    assert states(other.PullMessages({"Timeout": "PT0S", "MessageLimit": 64}), "PersonPresence") == ["true"]
    initial = pull.PullMessages({"Timeout": "PT0S", "MessageLimit": 64})
    assert states(initial, "PersonPresence") == ["true"]
    topic = pull.history.last_received["envelope"].find(".//{http://docs.oasis-open.org/wsn/b-2}Topic")
    assert topic.text == "cv:Analytics/PersonPresence"
    assert topic.nsmap["cv"] == "urn:cybervisual:onvif:topics:1"
    response = requests.put(base + "/api/config", json={"confidence": 0.95}, timeout=5)
    assert response.status_code == 200
    deadline, disappeared = time.monotonic() + 5, []
    while time.monotonic() < deadline and not disappeared:
        disappeared += states(pull.PullMessages({"Timeout": "PT1S", "MessageLimit": 64}), "PersonPresence")
    assert disappeared == ["false"]
    assert states(other.PullMessages({"Timeout": "PT0S", "MessageLimit": 64}), "PersonPresence") == ["false"]
    make_event_service(client, other_address, "SubscriptionManagerBinding").Unsubscribe()
    manager.Renew({"TerminationTime": "PT60S"})
    pull.SetSynchronizationPoint()
    assert states(pull.PullMessages({"Timeout": "PT0S", "MessageLimit": 64}), "PersonPresence") == ["false"]
    manager.Unsubscribe()
    with pytest.raises(Exception, match="Invalid|subscription"):
        pull.PullMessages({"Timeout": "PT0S", "MessageLimit": 64})


def test_independent_client_controls_simulated_ptz(camera):
    runtime, client, base = camera
    ptz = client.create_ptz_service()
    assert ptz.GetNodes()[0].HomeSupported is True
    assert ptz.GetConfigurations()[0].token == "ptz0"
    options = ptz.GetConfigurationOptions({"ConfigurationToken": "ptz0"})
    assert options.Spaces.AbsolutePanTiltPositionSpace[0].XRange.Min == -1
    ptz.AbsoluteMove({"ProfileToken": "raw", "Position": {"PanTilt": {"x": 0.3, "y": -0.2}}})
    assert ptz.GetStatus({"ProfileToken": "annotated"}).Position.PanTilt.x == pytest.approx(0.3)
    token = ptz.SetPreset({"ProfileToken": "raw", "PresetName": "Door"})
    ptz.GotoHomePosition({"ProfileToken": "raw"})
    assert ptz.GetStatus({"ProfileToken": "raw"}).Position.PanTilt.x == 0
    ptz.GotoPreset({"ProfileToken": "raw", "PresetToken": token})
    assert ptz.GetStatus({"ProfileToken": "raw"}).Position.PanTilt.y == pytest.approx(-0.2)
    ptz.ContinuousMove({"ProfileToken": "raw", "Velocity": {"PanTilt": {"x": 0.2, "y": 0}}, "Timeout": "PT0.1S"})
    time.sleep(0.2)
    assert ptz.GetStatus({"ProfileToken": "raw"}).MoveStatus.PanTilt == "IDLE"
    ptz.RelativeMove({"ProfileToken": "raw", "Translation": {"PanTilt": {"x": 0.1, "y": 0.1}}})
    assert ptz.GetStatus({"ProfileToken": "raw"}).Position.PanTilt.y == pytest.approx(-0.1)
    ptz.ContinuousMove({"ProfileToken": "raw", "Velocity": {"PanTilt": {"x": 1, "y": -1}}})
    time.sleep(2.1)
    state = ptz.GetStatus({"ProfileToken": "raw"})
    assert state.MoveStatus.PanTilt == "IDLE"
    assert state.Position.PanTilt.x == 1
    assert state.Position.PanTilt.y == -1
    ptz.Stop({"ProfileToken": "raw", "PanTilt": True})
    ptz.RemovePreset({"ProfileToken": "raw", "PresetToken": token})
    assert not ptz.GetPresets({"ProfileToken": "raw"})


def test_detector_fault_reports_unavailable_without_false_disappearance_or_stalling_raw(camera):
    runtime, client, base = camera
    reference = client.create_events_service().CreatePullPointSubscription({"InitialTerminationTime": "PT60S"})
    pull = make_event_service(client, reference.SubscriptionReference.Address._value_1, "PullPointSubscriptionBinding")
    initial = pull.PullMessages({"Timeout": "PT0S", "MessageLimit": 64})
    assert states(initial, "PersonPresence") == ["true"]
    response = requests.put(base + "/api/config", json={"detector_backend": "tensorrt",
                                                        "model_path": "/missing/model.engine"}, timeout=5)
    assert response.status_code == 200
    fault = pull.PullMessages({"Timeout": "PT1S", "MessageLimit": 64})
    assert states(fault, "AnalyticsOnline") == ["false"]
    assert states(fault, "PersonPresence") == []
    decode(stream_uri(client, "raw"), "tcp")
    assert runtime.raw_buffer.snapshot()["valid"]
    assert runtime.events.status()["presence"]["person"] is True
    assert not runtime.events.status()["online"]
    recovery = requests.put(base + "/api/config", json={"detector_backend": "mock"}, timeout=5)
    assert recovery.status_code == 200
    restored = pull.PullMessages({"Timeout": "PT5S", "MessageLimit": 64})
    assert states(restored, "AnalyticsOnline") == ["true"]
    assert states(restored, "PersonPresence") == []


def test_media2_schema_client_reads_profiles_and_encoder_settings(camera):
    runtime, camera_client, base = camera
    specifications = Path(__file__).with_name("specifications")
    bundle = Path(camera_client.wsdl_dir)

    class OfflineTransport(Transport):
        def load(self, url):
            name = Path(urlparse(url).path).name
            for directory in (specifications, bundle):
                for filename in (name, name + ".xsd"):
                    candidate = directory / filename
                    if candidate.is_file():
                        return candidate.read_bytes()
            raise AssertionError("Unresolved schema import: " + url)

    client = Client(str(specifications / "media2.wsdl"), transport=OfflineTransport(),
                    wsse=UsernameToken("viewer", "test-password", use_digest=True), settings=Settings(strict=True))
    media = client.create_service("{http://www.onvif.org/ver20/media/wsdl}Media2Binding", base + "/onvif/media2_service")
    capabilities = media.GetServiceCapabilities()
    assert capabilities.StreamingCapabilities.RTSPStreaming is True
    profiles = media.GetProfiles(Type=["All"])
    assert [profile.token for profile in profiles] == ["raw", "annotated"]
    assert profiles[0].Configurations.VideoEncoder.Encoding == "H264"
    assert profiles[0].Configurations.VideoEncoder.Resolution.Width == 320
    assert profiles[1].Configurations.VideoEncoder.RateControl.FrameRateLimit == 15
    assert media.GetStreamUri(Protocol="RtspUnicast", ProfileToken="raw").endswith("/raw")
    assert media.GetSnapshotUri(ProfileToken="annotated").endswith("/onvif/snapshot/annotated")
    encoders = media.GetVideoEncoderConfigurations(ConfigurationToken="raw-encoder")
    assert encoders[0].Profile == "Baseline"


def test_ws_discovery_over_udp_and_socket_release(camera):
    import xml.etree.ElementTree as ET
    from cybervisual.network_camera.discovery import DiscoveryResponder

    runtime, client, base = camera
    responder = DiscoveryResponder(runtime.network_camera, interface="127.0.0.1")
    envelope = ('<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope" '
                'xmlns:a="http://schemas.xmlsoap.org/ws/2004/08/addressing" '
                'xmlns:d="http://schemas.xmlsoap.org/ws/2005/04/discovery" '
                'xmlns:dn="http://www.onvif.org/ver10/network/wsdl">'
                '<s:Header><a:MessageID>urn:uuid:probe-test</a:MessageID></s:Header><s:Body>%s</s:Body></s:Envelope>')
    responder.start()
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(2)
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton("127.0.0.1"))
            sock.sendto((envelope % '<d:Probe><d:Types>dn:NetworkVideoTransmitter</d:Types></d:Probe>').encode(),
                        ("239.255.255.250", 3702))
            root = ET.fromstring(sock.recv(8192))
            assert root.find(".//{http://schemas.xmlsoap.org/ws/2005/04/discovery}XAddrs").text == base + "/onvif/device_service"
            address = root.find(".//{http://schemas.xmlsoap.org/ws/2004/08/addressing}Address").text
            assert address == "urn:uuid:" + runtime.network_camera.device_id
            sock.sendto((envelope % ('<d:Resolve><a:EndpointReference><a:Address>%s</a:Address>'
                                    '</a:EndpointReference></d:Resolve>' % address)).encode(), ("127.0.0.1", 3702))
            assert b"ResolveMatches" in sock.recv(8192)
    finally:
        responder.stop()
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        probe.bind(("127.0.0.1", 3702))


def test_same_profile_clients_share_encoder_and_survive_peer_disconnect(camera):
    runtime, client, base = camera
    uri = stream_uri(client, "raw")
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as workers:
        futures = [workers.submit(decode, uri, "tcp", frames) for frames in (3, 15)]
        deadline, sessions = time.monotonic() + 5, []
        while time.monotonic() < deadline:
            with runtime.network_camera._rtsp._lock:
                sessions = list(runtime.network_camera._rtsp._sessions)
            if runtime.network_camera._rtsp._server.get_session_pool().get_n_sessions() >= 2:
                break
            time.sleep(0.01)
        assert len([session for session in sessions if session["profile"] == "raw"]) == 1
        assert runtime.network_camera._rtsp._server.get_session_pool().get_n_sessions() >= 2
        assert all(future.result() for future in futures)


@pytest.mark.parametrize("account", ["", "viewer:wrong-password@"])
def test_rtsp_rejects_missing_or_invalid_credentials(camera, account):
    runtime, client, base = camera
    uri = stream_uri(client, "raw").replace("rtsp://", "rtsp://" + account, 1)
    result = subprocess.run(["ffmpeg", "-v", "error", "-rtsp_transport", "tcp", "-i", uri,
                             "-frames:v", "1", "-f", "null", "-"], capture_output=True, timeout=10)
    assert result.returncode != 0
    assert b"401" in result.stderr


def test_protocol_reconfiguration_releases_subscriptions_and_updates_capabilities(camera):
    runtime, client, base = camera
    identity = runtime.network_camera.device_id
    subscription = client.create_events_service().CreatePullPointSubscription({"InitialTerminationTime": "PT60S"})
    pull = make_event_service(client, subscription.SubscriptionReference.Address._value_1, "PullPointSubscriptionBinding")
    updated = requests.put(base + "/api/config", json={"network_camera": {"ptz_driver": "disabled"}}, timeout=5)
    assert updated.status_code == 200
    assert runtime.network_camera.status()["state"] == "running"
    assert runtime.network_camera.device_id == identity
    assert client.devicemgmt.GetCapabilities({"Category": "All"}).PTZ is None
    assert all(profile.PTZConfiguration is None for profile in client.create_media_service().GetProfiles())
    with pytest.raises(Exception, match="Invalid|subscription"):
        pull.PullMessages({"Timeout": "PT0S", "MessageLimit": 64})
    decode(stream_uri(client, "raw"), "tcp")


def test_camera_read_fault_reports_offline_and_recovers(camera, monkeypatch):
    from cybervisual.camera import CameraError
    from cybervisual import runtime as runtime_module

    runtime, client, base = camera
    reference = client.create_events_service().CreatePullPointSubscription({"InitialTerminationTime": "PT60S"})
    pull = make_event_service(client, reference.SubscriptionReference.Address._value_1, "PullPointSubscriptionBinding")
    assert states(pull.PullMessages({"Timeout": "PT0S", "MessageLimit": 64}), "PersonPresence") == ["true"]
    builder = runtime_module.build_frame_source

    class FailedSource:
        def open(self):
            raise CameraError("Integration test unplugged source")

        def close(self):
            pass

    def fail_read():
        raise CameraError("Integration test unplugged source")

    monkeypatch.setattr(runtime_module, "build_frame_source", lambda config: FailedSource())
    monkeypatch.setattr(runtime.frame_source, "read", fail_read)
    fault = pull.PullMessages({"Timeout": "PT2S", "MessageLimit": 64})
    assert states(fault, "AnalyticsOnline") == ["false"]
    assert states(fault, "PersonPresence") == []
    assert not runtime.raw_buffer.snapshot()["valid"]
    assert not runtime.buffer.snapshot()["valid"]
    monkeypatch.setattr(runtime_module, "build_frame_source", builder)
    recovery = pull.PullMessages({"Timeout": "PT5S", "MessageLimit": 64})
    assert states(recovery, "AnalyticsOnline") == ["true"]
    assert states(recovery, "PersonPresence") == []


def test_dashboard_ptz_and_independent_onvif_client_share_state(camera):
    runtime, client, base = camera
    response = requests.post(base + "/api/ptz/command", json={
        "action": "absolute_move", "pan": .5, "tilt": -.25}, timeout=5)
    assert response.status_code == 200
    ptz = client.create_ptz_service()
    position = ptz.GetStatus({"ProfileToken": "raw"}).Position.PanTilt
    assert position.x == pytest.approx(.5)
    assert position.y == pytest.approx(-.25)
    ptz.RelativeMove({"ProfileToken": "annotated", "Translation": {"PanTilt": {"x": -.2, "y": .1}}})
    state = requests.get(base + "/api/ptz", timeout=5).json()
    assert state["position"]["pan"] == pytest.approx(.3)
    token = ptz.SetPreset({"ProfileToken": "raw", "PresetName": "Dashboard shared"})
    requests.post(base + "/api/ptz/command", json={"action": "home"}, timeout=5).raise_for_status()
    requests.post(base + "/api/ptz/command", json={"action": "goto_preset", "token": token}, timeout=5).raise_for_status()
    assert ptz.GetStatus({"ProfileToken": "raw"}).Position.PanTilt.x == pytest.approx(.3)
    assert token in [preset["token"] for preset in requests.get(base + "/api/ptz", timeout=5).json()["presets"]]
    recent = requests.get(base + "/api/events/recent", timeout=5).json()
    assert recent["capacity"] == 200
    assert recent["status"]["online"]
    assert any(event["topic"] == "Device/AnalyticsOnline" for event in recent["events"])
