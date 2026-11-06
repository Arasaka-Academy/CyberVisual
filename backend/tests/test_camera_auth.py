import base64
import datetime
import hashlib
import os
import xml.etree.ElementTree as ET

import pytest

from cybervisual.network_camera.auth import DeviceCredentials
from cybervisual.network_camera.soap import NS, SOAPFault, parse_xml


def token(password="test-password", created=None, nonce=None):
    created = created or datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    nonce = nonce or os.urandom(16)
    digest = base64.b64encode(hashlib.sha1(nonce + created.encode() + password.encode()).digest()).decode()
    root = ET.Element("Envelope")
    security = ET.SubElement(root, "{%s}Security" % NS["wsse"])
    user = ET.SubElement(security, "{%s}UsernameToken" % NS["wsse"])
    for key, value in (("Username", "viewer"), ("Password", digest), ("Nonce", base64.b64encode(nonce).decode())):
        item = ET.SubElement(user, "{%s}%s" % (NS["wsse"], key))
        item.text = value
        if key == "Password":
            item.set("Type", NS["wsse_password_digest"])
    ET.SubElement(user, "{%s}Created" % NS["wsu"]).text = created
    return root


def test_wsse_rejects_wrong_password_stale_timestamp_and_replay():
    credentials = DeviceCredentials("viewer", "test-password")
    assert credentials.verify_wsse(token(password="wrong")) is False
    assert credentials.verify_wsse(token(created="2000-01-01T00:00:00Z")) is False
    request = token()
    assert credentials.verify_wsse(request) is True
    assert credentials.verify_wsse(request) is False
    assert credentials.verify_wsse(token()) is True


def test_wsse_rejects_replay_with_alternate_base64_padding_bits():
    credentials = DeviceCredentials("viewer", "test-password")
    request = token(nonce=b"\x00" * 16)
    nonce = request.find(".//wsse:Nonce", NS)
    original = nonce.text
    assert original.endswith("A==")
    assert credentials.verify_wsse(request)
    nonce.text = original[:-3] + "B=="
    assert base64.b64decode(nonce.text, validate=True) == base64.b64decode(original, validate=True)
    assert not credentials.verify_wsse(request)


def test_xml_entities_are_rejected():
    with pytest.raises(SOAPFault):
        parse_xml(b'<!DOCTYPE x [<!ENTITY secret SYSTEM "file:///etc/passwd">]><x>&secret;</x>')


def test_xml_size_is_bounded():
    with pytest.raises(SOAPFault):
        parse_xml(b"<x>" + b"x" * 300000 + b"</x>")


def test_http_digest_rejects_replay_wrong_password_and_uri():
    from requests.auth import HTTPDigestAuth
    from werkzeug.http import parse_dict_header

    credentials = DeviceCredentials("viewer", "test-password")

    def authorization(password="test-password"):
        auth = HTTPDigestAuth("viewer", password)
        auth.init_per_thread_state()
        auth._thread_local.chal = parse_dict_header(credentials.challenge()[7:])
        return auth.build_digest_header("GET", "http://camera/onvif/snapshot/raw")

    header = authorization()
    assert not credentials.verify_digest("GET", "/onvif/snapshot/annotated", header)
    assert not credentials.verify_digest("GET", "/onvif/snapshot/raw", authorization("wrong"))
    assert credentials.verify_digest("GET", "/onvif/snapshot/raw", header)
    assert not credentials.verify_digest("GET", "/onvif/snapshot/raw", header)
