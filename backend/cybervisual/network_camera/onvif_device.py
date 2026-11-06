import datetime
import platform

from .soap import NS, SOAPFault, add, node, text


SERVICES = (("tds", "device_service"), ("trt", "media_service"),
            ("tr2", "media2_service"), ("tev", "events_service"), ("tptz", "ptz_service"))


def service_capabilities(prefix):
    result = node(prefix + ":Capabilities")
    if prefix == "tds":
        add(result, "tds:Network", IPFilter="false", ZeroConfiguration="false", IPVersion6="false", DynDNS="false")
        add(result, "tds:Security", **{"TLS1.0": "false", "TLS1.1": "false", "TLS1.2": "false"},
            OnboardKeyGeneration="false", AccessPolicyConfig="false", DefaultAccessPolicy="false",
            Dot1X="false", RemoteUserHandling="false", X509Token="false", SAMLToken="false",
            KerberosToken="false", UsernameToken="true", HttpDigest="true", RELToken="false")
        add(result, "tds:System", DiscoveryResolve="true", DiscoveryBye="true", RemoteDiscovery="false",
            SystemBackup="false", SystemLogging="false", FirmwareUpgrade="false")
    elif prefix in ("trt", "tr2"):
        result.set("SnapshotUri", "true")
        add(result, prefix + ":ProfileCapabilities", MaximumNumberOfProfiles="2")
        streaming = add(result, prefix + ":StreamingCapabilities", RTPMulticast="false", RTP_RTSP_TCP="true")
        streaming.set("RTSPStreaming" if prefix == "tr2" else "RTP_TCP", "true")
    elif prefix == "tev":
        result.attrib.update(WSPullPointSupport="true", WSSubscriptionPolicySupport="false",
                             WSPausableSubscriptionManagerInterfaceSupport="false", MaxPullPoints="16")
    return result


def device_request(server, operation, request):
    response = node("tds:" + operation + "Response")
    if operation == "GetSystemDateAndTime":
        current = datetime.datetime.utcnow()
        value = add(response, "tds:SystemDateAndTime")
        add(value, "tt:DateTimeType", "Manual")
        add(value, "tt:DaylightSavings", "false")
        add(add(value, "tt:TimeZone"), "tt:TZ", "UTC0")
        date_time = add(value, "tt:UTCDateTime")
        date, clock = add(date_time, "tt:Time"), add(date_time, "tt:Date")
        for key, value in (("Hour", current.hour), ("Minute", current.minute), ("Second", current.second)):
            add(date, "tt:" + key, value)
        for key, value in (("Year", current.year), ("Month", current.month), ("Day", current.day)):
            add(clock, "tt:" + key, value)
    elif operation == "GetDeviceInformation":
        for key, value in (("Manufacturer", "CyberVisual"), ("Model", "CyberVisual Edge Camera"),
                           ("FirmwareVersion", "0.1.0"), ("SerialNumber", server.device_id),
                           ("HardwareId", platform.machine())):
            add(response, "tds:" + key, value)
    elif operation == "GetServices":
        include = text(request, "tds:IncludeCapability", "false") in ("true", "1")
        for prefix, path in SERVICES:
            if prefix == "tptz" and not server.ptz.enabled:
                continue
            service = add(response, "tds:Service")
            add(service, "tds:Namespace", NS[prefix])
            add(service, "tds:XAddr", server.http_url("/onvif/" + path))
            if include:
                add(service, "tds:Capabilities").append(service_capabilities(prefix))
            version = add(service, "tds:Version")
            add(version, "tt:Major", 2)
            add(version, "tt:Minor", 6)
    elif operation == "GetServiceCapabilities":
        response.append(service_capabilities("tds"))
    elif operation == "GetCapabilities":
        requested = [item.text for item in request.findall("tds:Category", NS)]
        if not requested:
            requested = ["All"]
        if set(requested) - {"All", "Device", "Media", "Events", "PTZ", "Analytics", "Imaging"}:
            raise SOAPFault("ter:InvalidArgVal", "Unknown capability category.")
        capabilities = add(response, "tds:Capabilities")
        if "All" in requested or "Device" in requested:
            device = add(capabilities, "tt:Device")
            add(device, "tt:XAddr", server.http_url("/onvif/device_service"))
            network = add(device, "tt:Network")
            for name in ("IPFilter", "ZeroConfiguration", "IPVersion6", "DynDNS"):
                add(network, "tt:" + name, "false")
            system = add(device, "tt:System")
            for name in ("DiscoveryResolve", "DiscoveryBye", "RemoteDiscovery", "SystemBackup", "SystemLogging", "FirmwareUpgrade"):
                add(system, "tt:" + name, "true" if name in ("DiscoveryResolve", "DiscoveryBye") else "false")
            version = add(system, "tt:SupportedVersions")
            add(version, "tt:Major", 2)
            add(version, "tt:Minor", 6)
            io = add(device, "tt:IO")
            add(io, "tt:InputConnectors", 0)
            add(io, "tt:RelayOutputs", 0)
            security = add(device, "tt:Security")
            for name in ("TLS1.1", "TLS1.2", "OnboardKeyGeneration", "AccessPolicyConfig", "X.509Token", "SAMLToken", "KerberosToken", "RELToken"):
                add(security, "tt:" + name, "false")
        if "All" in requested or "Events" in requested:
            events = add(capabilities, "tt:Events")
            add(events, "tt:XAddr", server.http_url("/onvif/events_service"))
            add(events, "tt:WSSubscriptionPolicySupport", "false")
            add(events, "tt:WSPullPointSupport", "true")
            add(events, "tt:WSPausableSubscriptionManagerInterfaceSupport", "false")
        if "All" in requested or "Media" in requested:
            media = add(capabilities, "tt:Media")
            add(media, "tt:XAddr", server.http_url("/onvif/media_service"))
            streaming = add(media, "tt:StreamingCapabilities")
            add(streaming, "tt:RTPMulticast", "false")
            add(streaming, "tt:RTP_TCP", "true")
            add(streaming, "tt:RTP_RTSP_TCP", "true")
        if server.ptz.enabled and ("All" in requested or "PTZ" in requested):
            add(add(capabilities, "tt:PTZ"), "tt:XAddr", server.http_url("/onvif/ptz_service"))
    elif operation == "GetScopes":
        for item in server.scopes():
            scope = add(response, "tds:Scopes")
            add(scope, "tt:ScopeDef", "Fixed")
            add(scope, "tt:ScopeItem", item)
    elif operation == "GetHostname":
        info = add(response, "tds:HostnameInformation")
        add(info, "tt:FromDHCP", "false")
        add(info, "tt:Name", "CyberVisual")
    else:
        raise SOAPFault("ter:ActionNotSupported", "Device operation is not supported.")
    return response
