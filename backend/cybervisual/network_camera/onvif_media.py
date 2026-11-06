from .onvif_device import service_capabilities
from .onvif_ptz import configuration as ptz_configuration
from .soap import NS, SOAPFault, add, node, text


PROFILES = ("raw", "annotated")


def require_profile(value):
    if value not in PROFILES:
        raise SOAPFault("ter:NoProfile", "Unknown video profile token.")
    return value


def source_configuration(server, profile, name):
    config = server.runtime.get_config()
    result = node(name, token=profile + "-source")
    add(result, "tt:Name", "Original sensor" if profile == "raw" else "Annotated sensor")
    add(result, "tt:UseCount", 1)
    add(result, "tt:SourceToken", "camera0")
    add(result, "tt:Bounds", x=0, y=0, width=config["resolution"]["width"], height=config["resolution"]["height"])
    return result


def encoder_configuration(server, profile, name, media2=False):
    config = server.runtime.get_config()
    settings = config["network_camera"]
    fps = min(config["camera_fps"], settings[profile + "_fps"])
    result = node(name, token=profile + "-encoder")
    add(result, "tt:Name", "Original H.264" if profile == "raw" else "Detection H.264")
    add(result, "tt:UseCount", 1)
    add(result, "tt:Encoding", "H264")
    resolution = add(result, "tt:Resolution")
    add(resolution, "tt:Width", config["resolution"]["width"])
    add(resolution, "tt:Height", config["resolution"]["height"])
    if not media2:
        add(result, "tt:Quality", 5)
    rate = add(result, "tt:RateControl")
    add(rate, "tt:FrameRateLimit", fps)
    if not media2:
        add(rate, "tt:EncodingInterval", 1)
    add(rate, "tt:BitrateLimit", settings[profile + "_bitrate_kbps"])
    if not media2:
        h264 = add(result, "tt:H264")
        add(h264, "tt:GovLength", fps)
        add(h264, "tt:H264Profile", "Baseline")
    multicast = add(result, "tt:Multicast")
    address = add(multicast, "tt:Address")
    add(address, "tt:Type", "IPv4")
    add(address, "tt:IPv4Address", "0.0.0.0")
    add(multicast, "tt:Port", 0)
    add(multicast, "tt:TTL", 1)
    add(multicast, "tt:AutoStart", "false")
    if media2:
        add(result, "tt:Quality", 5)
        result.attrib.update(GovLength=str(fps), Profile="Baseline", GuaranteedFrameRate="false")
    else:
        add(result, "tt:SessionTimeout", "PT60S")
    return result


def media_profile(server, profile, name, media2=False, types=None):
    result = node(name, token=profile, fixed="true")
    add(result, "tr2:Name" if media2 else "tt:Name", "Original" if profile == "raw" else "AI annotated")
    if media2:
        if not types:
            return result
        configurations = add(result, "tr2:Configurations")
        if "All" in types or "VideoSource" in types:
            configurations.append(source_configuration(server, profile, "tr2:VideoSource"))
        if "All" in types or "VideoEncoder" in types:
            configurations.append(encoder_configuration(server, profile, "tr2:VideoEncoder", True))
        if server.ptz.enabled and ("All" in types or "PTZ" in types):
            configurations.append(ptz_configuration("tr2:PTZ"))
    else:
        result.append(source_configuration(server, profile, "tt:VideoSourceConfiguration"))
        result.append(encoder_configuration(server, profile, "tt:VideoEncoderConfiguration"))
        if server.ptz.enabled:
            result.append(ptz_configuration("tt:PTZConfiguration"))
    return result


def media_request(server, prefix, operation, request):
    media2 = prefix == "tr2"
    response = node(prefix + ":" + operation + "Response")
    profile = text(request, prefix + ":ProfileToken")
    if profile is not None:
        require_profile(profile)
    if operation == "GetServiceCapabilities":
        response.append(service_capabilities(prefix))
    elif operation == "GetProfiles":
        tokens = [item.text for item in request.findall("tr2:Token", NS)] if media2 else []
        types = [item.text for item in request.findall("tr2:Type", NS)] if media2 else None
        for token in tokens:
            require_profile(token)
        for token in tokens or PROFILES:
            response.append(media_profile(server, token, prefix + ":Profiles", media2, types))
    elif operation == "GetProfile" and not media2:
        response.append(media_profile(server, require_profile(profile), "trt:Profile"))
    elif operation in ("GetStreamUri", "GetSnapshotUri"):
        require_profile(profile)
        if operation == "GetStreamUri":
            if media2:
                if text(request, "tr2:Protocol") not in ("RTSP", "RtspUnicast"):
                    raise SOAPFault("ter:InvalidStreamSetup", "Only unicast RTSP over UDP or TCP is supported.")
            else:
                stream = text(request, "trt:StreamSetup/tt:Stream", "RTP-Unicast")
                protocol = text(request, "trt:StreamSetup/tt:Transport/tt:Protocol", "RTSP")
                if stream != "RTP-Unicast" or protocol not in ("UDP", "TCP", "RTSP"):
                    raise SOAPFault("ter:InvalidStreamSetup", "Only unicast RTSP over UDP or TCP is supported.")
            uri = server.rtsp_url(profile)
        else:
            uri = server.http_url("/onvif/snapshot/" + profile)
        if media2:
            add(response, "tr2:Uri", uri)
        else:
            value = add(response, "trt:MediaUri")
            add(value, "tt:Uri", uri)
            add(value, "tt:InvalidAfterConnect", "false")
            add(value, "tt:InvalidAfterReboot", "false")
            add(value, "tt:Timeout", "PT0S")
    elif operation == "GetVideoSources" and not media2:
        config = server.runtime.get_config()
        value = add(response, "trt:VideoSources", token="camera0")
        add(value, "tt:Framerate", config["camera_fps"])
        resolution = add(value, "tt:Resolution")
        add(resolution, "tt:Width", config["resolution"]["width"])
        add(resolution, "tt:Height", config["resolution"]["height"])
    elif operation in ("GetVideoSourceConfigurations", "GetVideoEncoderConfigurations",
                       "GetCompatibleVideoSourceConfigurations", "GetCompatibleVideoEncoderConfigurations",
                       "GetVideoSourceConfiguration", "GetVideoEncoderConfiguration"):
        encoder = "Encoder" in operation
        suffix = "-encoder" if encoder else "-source"
        token = text(request, prefix + ":ConfigurationToken")
        selected = list(PROFILES)
        if token is not None:
            selected = [p for p in PROFILES if p + suffix == token]
            if not selected:
                raise SOAPFault("ter:NoConfig", "Unknown video configuration token.")
        if profile:
            selected = [p for p in selected if p == profile]
        singular = operation.endswith("Configuration")
        if singular and token is None:
            raise SOAPFault("ter:InvalidArgVal", "A configuration token is required.")
        for item in selected:
            name = prefix + (":Configuration" if singular else ":Configurations")
            response.append(encoder_configuration(server, item, name, media2) if encoder
                            else source_configuration(server, item, name))
    else:
        raise SOAPFault("ter:ActionNotSupported", "Media operation is not supported; encoder settings are configured locally.")
    return response
