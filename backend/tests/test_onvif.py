import base64
import datetime
import hashlib
import os
import xml.etree.ElementTree as ET

import pytest

from cybervisual.app import create_app
from cybervisual.config import DEFAULT_CONFIG, merge_config
from cybervisual.runtime import RuntimeService


SOAP = "http://www.w3.org/2003/05/soap-envelope"
DEVICE = "http://www.onvif.org/ver10/device/wsdl"
MEDIA = "http://www.onvif.org/ver10/media/wsdl"
WSSE = "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd"
WSU = "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd"


def soap_document(namespace, operation, authenticated=True, children=""):
    root = ET.fromstring('<s:Envelope xmlns:s="%s"><s:Header/><s:Body><op:%s xmlns:op="%s">%s</op:%s></s:Body></s:Envelope>'
                         % (SOAP, operation, namespace, children, operation))
    if authenticated:
        security = ET.SubElement(root[0], "{%s}Security" % WSSE)
        token = ET.SubElement(security, "{%s}UsernameToken" % WSSE)
        nonce = os.urandom(16)
        created = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        digest = base64.b64encode(hashlib.sha1(nonce + created.encode() + b"test-password").digest()).decode()
        ET.SubElement(token, "{%s}Username" % WSSE).text = "viewer"
        password = ET.SubElement(token, "{%s}Password" % WSSE)
        password.text = digest
        password.set("Type", "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-username-token-profile-1.0#PasswordDigest")
        ET.SubElement(token, "{%s}Nonce" % WSSE).text = base64.b64encode(nonce).decode()
        ET.SubElement(token, "{%s}Created" % WSU).text = created
    return ET.tostring(root)


@pytest.fixture
def camera_app(monkeypatch, tmp_path):
    monkeypatch.setenv("CYBERVISUAL_ONVIF_USERNAME", "viewer")
    monkeypatch.setenv("CYBERVISUAL_ONVIF_PASSWORD", "test-password")
    monkeypatch.setenv("CYBERVISUAL_STATE_DIR", str(tmp_path))
    config = merge_config(DEFAULT_CONFIG, {"network_camera": {"enabled": True, "advertise_host": "127.0.0.1"}})
    runtime = RuntimeService(config=config)
    return create_app(runtime=runtime, auto_start=False)


def test_services_require_authentication_but_time_query_allows_clock_sync(camera_app):
    client = camera_app.test_client()
    denied = client.post("/onvif/device_service", data=soap_document(DEVICE, "GetDeviceInformation", False))
    assert denied.status_code == 401
    assert b"NotAuthorized" in denied.data
    clock = client.post("/onvif/device_service", data=soap_document(DEVICE, "GetSystemDateAndTime", False))
    assert clock.status_code == 200
    assert b"UTCDateTime" in clock.data


def test_profiles_snapshot_and_uris_are_separate_without_credentials(camera_app):
    client = camera_app.test_client()
    response = client.post("/onvif/media_service", data=soap_document(MEDIA, "GetProfiles"))
    assert response.status_code == 200
    root = ET.fromstring(response.data)
    profiles = root.findall(".//{%s}Profiles" % MEDIA)
    assert [p.get("token") for p in profiles] == ["raw", "annotated"]
    for profile in ("raw", "annotated"):
        response = client.post("/onvif/media_service", data=soap_document(MEDIA, "GetStreamUri", children=
            '<op:StreamSetup xmlns:tt="http://www.onvif.org/ver10/schema"><tt:Stream>RTP-Unicast</tt:Stream>'
            '<tt:Transport><tt:Protocol>RTSP</tt:Protocol></tt:Transport></op:StreamSetup><op:ProfileToken>%s</op:ProfileToken>' % profile))
        assert response.status_code == 200
        assert ("rtsp://127.0.0.1:8554/" + profile).encode() in response.data
        assert b"test-password" not in response.data


def test_identity_is_persistent_and_disabled_ptz_is_not_advertised(camera_app):
    client = camera_app.test_client()
    result = client.post("/onvif/device_service", data=soap_document(DEVICE, "GetCapabilities"))
    assert result.status_code == 200
    assert b"ptz_service" not in result.data
    first = client.post("/onvif/device_service", data=soap_document(DEVICE, "GetDeviceInformation"))
    second = client.post("/onvif/device_service", data=soap_document(DEVICE, "GetDeviceInformation"))
    root = ET.fromstring(first.data)
    assert root.find(".//{%s}SerialNumber" % DEVICE).text == ET.fromstring(second.data).find(".//{%s}SerialNumber" % DEVICE).text
    from cybervisual.network_camera.server import NetworkCameraService
    runtime = RuntimeService(config=camera_app.config["runtime"].get_config())
    restarted = NetworkCameraService(runtime)
    assert restarted.device_id == root.find(".//{%s}SerialNumber" % DEVICE).text


def test_unsupported_method_and_invalid_profile_return_faults(camera_app):
    client = camera_app.test_client()
    response = client.post("/onvif/device_service", data=soap_document(DEVICE, "SystemReboot"))
    assert response.status_code == 400
    assert b"ActionNotSupported" in response.data
    response = client.post("/onvif/media_service", data=soap_document(MEDIA, "GetProfile", children="<op:ProfileToken>missing</op:ProfileToken>"))
    assert response.status_code == 400
    assert b"NoProfile" in response.data


def test_network_endpoints_are_absent_when_disabled():
    app = create_app(runtime=RuntimeService(config=dict(DEFAULT_CONFIG)), auto_start=False)
    assert app.test_client().post("/onvif/device_service", data=soap_document(DEVICE, "GetServices")).status_code == 404


def test_events_use_wsdl_response_action(camera_app):
    client = camera_app.test_client()
    namespace = "http://www.onvif.org/ver10/events/wsdl"
    result = client.post("/onvif/events_service", data=soap_document(namespace, "GetEventProperties"))
    assert result.status_code == 200
    root = ET.fromstring(result.data)
    action = root.find(".//{http://www.w3.org/2005/08/addressing}Action").text
    assert action == namespace + "/EventPortType/GetEventPropertiesResponse"


def test_service_capabilities_use_schema_attribute_names(camera_app):
    result = camera_app.test_client().post("/onvif/device_service",
                                          data=soap_document(DEVICE, "GetServiceCapabilities"))
    security = ET.fromstring(result.data).find(".//{%s}Security" % DEVICE)
    assert security.get("TLS1.2") == "false"
    assert "TLS1_2" not in security.attrib


def test_snapshot_digest_replay_and_profile_dimensions(camera_app):
    from io import BytesIO
    import numpy as np
    from PIL import Image
    from requests.auth import HTTPDigestAuth
    from werkzeug.http import parse_dict_header

    runtime = camera_app.config["runtime"]
    runtime.raw_buffer.publish(np.zeros((120, 160, 3), dtype=np.uint8), None, [])
    client = camera_app.test_client()
    path = "/onvif/snapshot/raw"
    denied = client.get(path)
    assert denied.status_code == 401
    auth = HTTPDigestAuth("viewer", "test-password")
    auth.init_per_thread_state()
    auth._thread_local.chal = parse_dict_header(denied.headers["WWW-Authenticate"][7:])
    header = auth.build_digest_header("GET", "http://camera" + path)
    snapshot = client.get(path, headers={"Authorization": header})
    assert snapshot.status_code == 200
    assert Image.open(BytesIO(snapshot.data)).size == (640, 480)
    assert client.get(path, headers={"Authorization": header}).status_code == 401


def test_unready_ptz_driver_returns_service_fault(camera_app):
    from cybervisual.network_camera.ptz import PTZController, PTZUnavailable

    class UnreadyDriver:
        def status(self):
            raise PTZUnavailable("Driver has not completed calibration")

    service = camera_app.config["runtime"].network_camera
    service._prepare()
    service._ptz = PTZController(UnreadyDriver())
    namespace = "http://www.onvif.org/ver20/ptz/wsdl"
    result = camera_app.test_client().post("/onvif/ptz_service", data=soap_document(namespace, "GetStatus",
                                                       children="<op:ProfileToken>raw</op:ProfileToken>"))
    assert result.status_code == 503
    assert b"ServiceNotAvailable" in result.data
    assert b"PTZ driver is not ready" in result.data
