from .soap import NS, SOAPFault, add, duration, node, text, utc


POSITION_SPACE = "http://www.onvif.org/ver10/tptz/PanTiltSpaces/PositionGenericSpace"
TRANSLATION_SPACE = "http://www.onvif.org/ver10/tptz/PanTiltSpaces/TranslationGenericSpace"
VELOCITY_SPACE = "http://www.onvif.org/ver10/tptz/PanTiltSpaces/VelocityGenericSpace"


def ranges(parent, name, minimum=-1, maximum=1):
    value = add(parent, "tt:" + name)
    add(value, "tt:Min", minimum)
    add(value, "tt:Max", maximum)


def spaces(parent):
    for name, uri in (("AbsolutePanTiltPositionSpace", POSITION_SPACE),
                      ("RelativePanTiltTranslationSpace", TRANSLATION_SPACE),
                      ("ContinuousPanTiltVelocitySpace", VELOCITY_SPACE)):
        space = add(parent, "tt:" + name)
        add(space, "tt:URI", uri)
        ranges(space, "XRange")
        ranges(space, "YRange")


def configuration(name="tptz:PTZConfiguration"):
    result = node(name, token="ptz0")
    add(result, "tt:Name", "CyberVisual Pan/Tilt")
    add(result, "tt:UseCount", 2)
    add(result, "tt:NodeToken", "ptz0")
    add(result, "tt:DefaultAbsolutePantTiltPositionSpace", POSITION_SPACE)
    add(result, "tt:DefaultRelativePanTiltTranslationSpace", TRANSLATION_SPACE)
    add(result, "tt:DefaultContinuousPanTiltVelocitySpace", VELOCITY_SPACE)
    add(result, "tt:DefaultPTZTimeout", "PT2S")
    limits = add(add(result, "tt:PanTiltLimits"), "tt:Range")
    add(limits, "tt:URI", POSITION_SPACE)
    ranges(limits, "XRange")
    ranges(limits, "YRange")
    return result


def vector(parent, name, pan, tilt):
    result = add(parent, name)
    add(result, "tt:PanTilt", x=pan, y=tilt, space=POSITION_SPACE)
    return result


def ptz_request(server, operation, request):
    controller = server.ptz
    if not controller.enabled:
        raise SOAPFault("ter:ActionNotSupported", "PTZ driver is disabled.")
    for name, allowed in (("ProfileToken", ("raw", "annotated")), ("NodeToken", ("ptz0",)),
                          ("PTZConfigurationToken", ("ptz0",)), ("ConfigurationToken", ("ptz0",))):
        token = text(request, "tptz:" + name)
        if token is not None and token not in allowed:
            raise SOAPFault("ter:InvalidArgVal", "Unknown PTZ or profile token.")
    if request.find("tptz:Speed", NS) is not None:
        raise SOAPFault("ter:ActionNotSupported", "Position moves use the driver's default speed; use ContinuousMove for velocity control.")
    if request.find(".//tt:Zoom", NS) is not None or text(request, "tptz:Zoom") in ("true", "1"):
        raise SOAPFault("ter:ActionNotSupported", "This camera has no zoom axis.")
    response = node("tptz:" + operation + "Response")
    if operation == "GetServiceCapabilities":
        add(response, "tptz:Capabilities", EFlip="false", Reverse="false", GetCompatibleConfigurations="true",
            MoveStatus="true", StatusPosition="true")
    elif operation in ("GetNodes", "GetNode"):
        ptz_node = add(response, "tptz:PTZNode", token="ptz0", FixedHomePosition="true")
        add(ptz_node, "tt:Name", controller.capabilities()["name"])
        spaces(add(ptz_node, "tt:SupportedPTZSpaces"))
        add(ptz_node, "tt:MaximumNumberOfPresets", 32)
        add(ptz_node, "tt:HomeSupported", "true")
    elif operation in ("GetConfigurations", "GetConfiguration", "GetCompatibleConfigurations"):
        response.append(configuration())
    elif operation == "GetConfigurationOptions":
        options = add(response, "tptz:PTZConfigurationOptions")
        spaces(add(options, "tt:Spaces"))
        ranges(options, "PTZTimeout", "PT0.1S", "PT30S")
    elif operation == "GetStatus":
        state = controller.status()
        status = add(response, "tptz:PTZStatus")
        vector(status, "tt:Position", state["pan"], state["tilt"])
        add(add(status, "tt:MoveStatus"), "tt:PanTilt", "MOVING" if state["moving"] else "IDLE")
        add(status, "tt:UtcTime", utc())
    elif operation in ("AbsoluteMove", "RelativeMove", "ContinuousMove"):
        name, expected_space = {"AbsoluteMove": ("Position", POSITION_SPACE),
                                "RelativeMove": ("Translation", TRANSLATION_SPACE),
                                "ContinuousMove": ("Velocity", VELOCITY_SPACE)}[operation]
        coordinates = request.find("tptz:%s/tt:PanTilt" % name, NS)
        if coordinates is None or coordinates.get("space", expected_space) != expected_space:
            raise SOAPFault("ter:InvalidArgVal", "A supported PanTilt coordinate space is required.")
        pan, tilt = float(coordinates.get("x", "nan")), float(coordinates.get("y", "nan"))
        if operation == "AbsoluteMove":
            controller.absolute_move(pan, tilt)
        elif operation == "RelativeMove":
            controller.relative_move(pan, tilt)
        else:
            controller.continuous_move(pan, tilt, duration(text(request, "tptz:Timeout"), 2))
    elif operation == "Stop":
        if text(request, "tptz:PanTilt", "true") not in ("false", "0"):
            controller.stop()
    elif operation == "GotoHomePosition":
        controller.home()
    elif operation == "GetPresets":
        for preset in controller.presets():
            item = add(response, "tptz:Preset", token=preset["token"])
            add(item, "tt:Name", preset["name"])
            vector(item, "tt:PTZPosition", preset["pan"], preset["tilt"])
    elif operation == "SetPreset":
        token = controller.set_preset(text(request, "tptz:PresetName", "Preset"), text(request, "tptz:PresetToken"))
        add(response, "tptz:PresetToken", token)
    elif operation == "GotoPreset":
        controller.goto_preset(text(request, "tptz:PresetToken"))
    elif operation == "RemovePreset":
        controller.remove_preset(text(request, "tptz:PresetToken"))
    else:
        raise SOAPFault("ter:ActionNotSupported", "PTZ operation is not supported.")
    return response
