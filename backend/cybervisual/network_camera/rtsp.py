import threading
import time

import numpy as np
from PIL import Image


class RTSPServer(object):
    """One shared GStreamer media factory (and encoder) per video profile."""

    _media_type = None

    def __init__(self, runtime, settings, credentials):
        self.runtime, self.settings, self.credentials = runtime, settings, credentials
        self.encoder = None
        self._server = self._loop = self._context = self._source = None
        self._cleanup_source = None
        self._thread = None
        self._sessions = []
        self._lock = threading.RLock()
        self._errors = {}
        self._frames = {"raw": 0, "annotated": 0}

    def start(self):
        try:
            import gi
            gi.require_version("Gst", "1.0")
            gi.require_version("GstRtsp", "1.0")
            gi.require_version("GstRtspServer", "1.0")
            from gi.repository import GLib, Gst, GstRtsp, GstRtspServer
        except (ImportError, ValueError):
            raise RuntimeError("Install Python GI and GStreamer RTSP Server system packages.")
        self.Gst, self.GLib, self.GstRtspServer = Gst, GLib, GstRtspServer
        Gst.init(None)
        if RTSPServer._media_type is None:
            class ObservedRTSPMedia(GstRtspServer.RTSPMedia):
                def do_handle_message(self, message):
                    callback = getattr(self, "_camera_error_callback", None)
                    if message.type == Gst.MessageType.ERROR and callback:
                        callback()
                    return GstRtspServer.RTSPMedia.do_handle_message(self, message)

            RTSPServer._media_type = ObservedRTSPMedia
        requested = self.settings["encoder"]
        hardware = bool(Gst.ElementFactory.find("nvv4l2h264enc") and Gst.ElementFactory.find("nvvidconv"))
        self.encoder = "nvv4l2h264enc" if requested != "software" and hardware else "x264enc"
        if requested == "jetson" and not hardware:
            raise RuntimeError("Jetson H.264 hardware encoder is unavailable.")
        if not Gst.ElementFactory.find(self.encoder):
            raise RuntimeError("H.264 encoder %s is unavailable." % self.encoder)
        self._context = GLib.MainContext.new()
        self._loop = GLib.MainLoop.new(self._context, False)
        self._server = GstRtspServer.RTSPServer.new()
        self._server.set_address("0.0.0.0")
        self._server.set_service(str(self.settings["rtsp_port"]))
        auth = GstRtspServer.RTSPAuth.new()
        auth.set_supported_methods(GstRtsp.RTSPAuthMethod.DIGEST)
        token = GstRtspServer.RTSPToken.new()
        token.set_string("media.factory.role", "camera")
        self.credentials.configure_rtsp_auth(auth, token)
        self._server.set_auth(auth)
        mounts = self._server.get_mount_points()
        for profile in ("raw", "annotated"):
            pipeline = self._pipeline(profile)
            # Validate elements and JetPack-compatible properties before advertising.
            probe = Gst.parse_launch(pipeline)
            probe.set_state(Gst.State.NULL)
            factory = GstRtspServer.RTSPMediaFactory.new()
            factory.set_media_gtype(RTSPServer._media_type)
            factory.set_launch(pipeline)
            factory.set_shared(True)
            factory.set_protocols(GstRtsp.RTSPLowerTrans.UDP | GstRtsp.RTSPLowerTrans.TCP)
            permissions = Gst.Structure.new_empty("camera")
            permissions.set_value("media.factory.access", True)
            permissions.set_value("media.factory.construct", True)
            factory.add_role_from_structure(permissions)
            factory.connect("media-configure", self._configure_media, profile)
            mounts.add_factory("/" + profile, factory)
        source_id = self._server.attach(self._context)
        if not source_id:
            self.stop()
            raise RuntimeError("Unable to bind the configured RTSP port.")
        self._source = self._context.find_source_by_id(source_id)
        pool = self._server.get_session_pool()

        def cleanup_sessions(*args):
            pool.cleanup()
            return True

        # GstRTSPServer does not expire abandoned sessions on its own.
        self._cleanup_source = GLib.timeout_source_new_seconds(1)
        self._cleanup_source.set_callback(cleanup_sessions)
        self._cleanup_source.attach(self._context)
        self._thread = threading.Thread(target=self._run, name="cybervisual-rtsp")
        self._thread.daemon = True
        self._thread.start()

    def _run(self):
        self._context.push_thread_default()
        try:
            self._loop.run()
        finally:
            self._context.pop_thread_default()

    def _pipeline(self, profile):
        config = self.runtime.get_config()
        width, height = config["resolution"]["width"], config["resolution"]["height"]
        fps = min(config["camera_fps"], self.settings[profile + "_fps"])
        bitrate = self.settings[profile + "_bitrate_kbps"]
        source = ('appsrc name=source is-live=true format=time block=false max-bytes=%d '
                  'caps="video/x-raw,format=RGB,width=%d,height=%d,framerate=%d/1" '
                  '! queue max-size-buffers=1 max-size-bytes=0 max-size-time=0 leaky=downstream '
                  '! videoconvert ! video/x-raw,format=I420 ' % (width * height * 6, width, height, fps))
        if self.encoder == "nvv4l2h264enc":
            encoder = ('! nvvidconv ! video/x-raw(memory:NVMM),format=NV12 '
                       '! nvv4l2h264enc bitrate=%d insert-sps-pps=true iframeinterval=%d ' % (bitrate * 1000, fps))
        else:
            encoder = ('! x264enc tune=zerolatency speed-preset=ultrafast bitrate=%d '
                       'key-int-max=%d bframes=0 byte-stream=true ! video/x-h264,profile=baseline ' % (bitrate, fps))
        return '( %s %s ! h264parse ! rtph264pay name=pay0 pt=96 config-interval=1 )' % (source, encoder)

    def _configure_media(self, factory, media, profile):
        source = media.get_element().get_by_name("source")
        session = {"stop": threading.Event(), "demand": threading.Event(), "media": media, "profile": profile}
        source.connect("need-data", lambda *args: session["demand"].set())
        source.connect("enough-data", lambda *args: session["demand"].clear())
        media.connect("unprepared", lambda *args: session["stop"].set())

        def on_error():
            with self._lock:
                self._errors[profile] = "H.264 media pipeline failed. Check device GStreamer logs."
            session["stop"].set()

        # The media bin's initial bus is replaced when GstRTSPMedia prepares its
        # pipeline. Observe its message handler and preserve the parent handler.
        media._camera_error_callback = on_error
        with self._lock:
            self._sessions.append(session)
            self._errors.pop(profile, None)
        worker = threading.Thread(target=self._feed, args=(source, session), name="cybervisual-rtsp-" + profile)
        worker.daemon = True
        session["thread"] = worker
        worker.start()

    def _feed(self, source, session):
        profile = session["profile"]
        buffer = self.runtime.raw_buffer if profile == "raw" else self.runtime.buffer
        config = self.runtime.get_config()
        width, height = config["resolution"]["width"], config["resolution"]["height"]
        row_bytes = width * 3
        stride = (row_bytes + 3) & ~3
        fps = min(config["camera_fps"], self.settings[profile + "_fps"])
        version, first_stamp, last_pts = None, None, -1
        try:
            while not session["stop"].is_set():
                if not session["demand"].wait(0.2):
                    continue
                paced = time.monotonic()
                item = buffer.wait_for_frame(version, timeout=0.2)
                if item is None:
                    continue
                version = item["version"]
                frame = item["frame"]
                if frame.shape[:2] != (height, width):
                    resampling = getattr(Image, "Resampling", Image)
                    frame = np.asarray(Image.fromarray(frame).resize((width, height), resampling.BILINEAR))
                if stride == row_bytes:
                    payload = np.ascontiguousarray(frame, dtype=np.uint8).tobytes()
                else:
                    # GStreamer RGB caps imply a four-byte aligned row stride.
                    rows = np.zeros((height, stride), dtype=np.uint8)
                    rows[:, :row_bytes] = np.asarray(frame, dtype=np.uint8).reshape(height, row_bytes)
                    payload = rows.tobytes()
                gst_buffer = self.Gst.Buffer.new_allocate(None, len(payload), None)
                gst_buffer.fill(0, payload)
                stamp = time.monotonic()
                if first_stamp is None:
                    first_stamp = stamp
                pts = max(last_pts + 1, int((stamp - first_stamp) * self.Gst.SECOND))
                gst_buffer.pts = gst_buffer.dts = pts
                gst_buffer.duration = self.Gst.SECOND // fps
                last_pts = pts
                if source.emit("push-buffer", gst_buffer) != self.Gst.FlowReturn.OK:
                    break
                with self._lock:
                    self._frames[profile] += 1
                session["stop"].wait(max(0, 1.0 / fps - (time.monotonic() - paced)))
        finally:
            source.emit("end-of-stream")
            session["media"]._camera_error_callback = None
            with self._lock:
                if session in self._sessions:
                    self._sessions.remove(session)

    def status(self):
        with self._lock:
            return {"encoder": self.encoder, "streams": {
                profile: {"active": any(s["profile"] == profile for s in self._sessions),
                          "frames": self._frames[profile], "last_error": self._errors.get(profile)}
                for profile in ("raw", "annotated")}}

    def stop(self):
        if self._cleanup_source:
            self._cleanup_source.destroy()
            self._cleanup_source = None
        with self._lock:
            sessions = list(self._sessions)
        for session in sessions:
            session["stop"].set()
        if self._server is not None:
            def close_client(server, client, data):
                client.close()
                return self.GstRtspServer.RTSPFilterResult.REMOVE
            self._server.client_filter(close_client, None)
        for session in sessions:
            session["thread"].join(timeout=1.0)
            session["media"].unprepare()
        if self._source:
            self._source.destroy()
        if self._loop:
            self._loop.quit()
        if self._thread:
            self._thread.join(timeout=2.0)
        self._server = self._loop = self._source = None
