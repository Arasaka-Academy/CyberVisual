import calendar
import datetime
import re
import uuid
import xml.etree.ElementTree as ET

from defusedxml.ElementTree import fromstring
from defusedxml.common import DefusedXmlException


NS = {
    "s": "http://www.w3.org/2003/05/soap-envelope",
    "tds": "http://www.onvif.org/ver10/device/wsdl",
    "trt": "http://www.onvif.org/ver10/media/wsdl",
    "tr2": "http://www.onvif.org/ver20/media/wsdl",
    "tptz": "http://www.onvif.org/ver20/ptz/wsdl",
    "tev": "http://www.onvif.org/ver10/events/wsdl",
    "tt": "http://www.onvif.org/ver10/schema",
    "wsnt": "http://docs.oasis-open.org/wsn/b-2",
    "wstop": "http://docs.oasis-open.org/wsn/t-1",
    "wsa": "http://www.w3.org/2005/08/addressing",
    "a": "http://schemas.xmlsoap.org/ws/2004/08/addressing",
    "d": "http://schemas.xmlsoap.org/ws/2005/04/discovery",
    "dn": "http://www.onvif.org/ver10/network/wsdl",
    "wsse": "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd",
    "wsu": "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd",
    "ter": "http://www.onvif.org/ver10/error",
    "xs": "http://www.w3.org/2001/XMLSchema",
    "cv": "urn:cybervisual:onvif:topics:1",
}
NS["wsse_password_digest"] = "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-username-token-profile-1.0#PasswordDigest"
for _prefix, _uri in NS.items():
    if _prefix != "wsse_password_digest":
        ET.register_namespace(_prefix, _uri)


def q(name):
    prefix, local = name.split(":", 1)
    return "{%s}%s" % (NS[prefix], local)


def node(name, text=None, **attributes):
    result = ET.Element(q(name), {key: str(value) for key, value in attributes.items()})
    if text is not None:
        result.text = str(text)
    return result


def add(parent, name, text=None, **attributes):
    result = node(name, text, **attributes)
    parent.append(result)
    return result


def text(parent, path, default=None):
    result = parent.find(path, NS)
    return default if result is None or result.text is None else result.text


def serialize(root):
    # QName-valued text (topics, fault codes, types) also needs namespace bindings.
    used = set()
    for item in root.iter():
        for name in [item.tag] + list(item.attrib):
            if name.startswith("{"):
                used.add(name[1:].split("}", 1)[0])
    for prefix, uri in NS.items():
        if prefix != "wsse_password_digest" and uri not in used:
            root.set("xmlns:" + prefix, uri)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def envelope(payload, action=None, relates_to=None):
    root = node("s:Envelope")
    header = add(root, "s:Header")
    if action:
        add(header, "wsa:Action", action)
        add(header, "wsa:MessageID", "urn:uuid:" + str(uuid.uuid4()))
    if relates_to:
        add(header, "wsa:RelatesTo", relates_to)
    add(root, "s:Body").append(payload)
    return serialize(root)


class SOAPFault(ValueError):
    def __init__(self, code, message, status=400):
        super(SOAPFault, self).__init__(message)
        self.code, self.status = code, status

    def xml(self):
        fault = node("s:Fault")
        code = add(fault, "s:Code")
        add(code, "s:Value", "s:Sender")
        add(add(code, "s:Subcode"), "s:Value", self.code)
        reason = add(add(fault, "s:Reason"), "s:Text", str(self))
        reason.set("{http://www.w3.org/XML/1998/namespace}lang", "en")
        return envelope(fault)


def parse_xml(data):
    if len(data) > 262144:
        raise SOAPFault("ter:InvalidArgVal", "SOAP document exceeds 256 KiB.", 413)
    try:
        return fromstring(data, forbid_dtd=True, forbid_entities=True, forbid_external=True)
    except (ET.ParseError, DefusedXmlException, ValueError):
        raise SOAPFault("ter:InvalidArgVal", "Malformed or unsafe XML.")


def utc(stamp=None):
    value = datetime.datetime.now(datetime.timezone.utc) if stamp is None else datetime.datetime.fromtimestamp(stamp, datetime.timezone.utc)
    return value.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def parse_utc(value):
    value = value.strip()
    if value.endswith("Z"):
        value = value[:-1] + "+0000"
    value = re.sub(r"([+-]\d\d):(\d\d)$", r"\1\2", value)
    for pattern in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            return datetime.datetime.strptime(value, pattern).timestamp()
        except ValueError:
            pass
    raise ValueError("Expected an ISO 8601 timestamp with timezone.")


def duration(value, default=60):
    if value is None:
        return float(default)
    match = re.match(r"^P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?)?$", value)
    if not match or not any(match.groups()) or value.endswith("T"):
        raise ValueError("Expected an ISO 8601 duration.")
    days, hours, minutes, seconds = match.groups()
    return float(days or 0) * 86400 + float(hours or 0) * 3600 + float(minutes or 0) * 60 + float(seconds or 0)
