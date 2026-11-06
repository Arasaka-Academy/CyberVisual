import json
import os
import threading
import time

from .buffer import LatestFrameBuffer
from .camera import CameraError, build_frame_source
from .config import load_config, merge_config, save_config
from .detector import MockDetector, build_detector
from .overlay import draw_overlay, encode_jpeg, placeholder_frame
from .sensors import read_system_metrics
from .network_camera.events import EventBroker


class RuntimeService(object):
    def __init__(self, config_path=None, config=None, frame_source=None, detector=None):
        self.config_path = config_path
        self.config = config or load_config(config_path)
        self.frame_source = frame_source
        self.detector = detector
        self.buffer = LatestFrameBuffer()
        self.raw_buffer = LatestFrameBuffer()
        self.events = EventBroker()
        self.network_camera = None
        self._lock = threading.RLock()
        self._capture_lock = threading.Lock()
        self._update_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread = None
        self._capture_thread = None
        self._generation = 0
        self._last_status = self._initial_status()
        self._frames = 0
        self._fps_window_started = time.time()
        self._last_auto_snapshot_attempt_at = None
        self._auto_snapshot_count = 0

    def start(self):
        with self._lock:
            if any(worker and worker.is_alive() for worker in (self._thread, self._capture_thread)):
                if self._stop_event.is_set():
                    raise RuntimeError("Runtime workers are still stopping; retry after the camera and detector return.")
                return
            self._stop_event.clear()
            self._capture_thread = threading.Thread(target=self._capture_loop, name="cybervisual-capture")
            self._capture_thread.daemon = True
            self._capture_thread.start()
            self._thread = threading.Thread(target=self._run, name="cybervisual-runtime")
            self._thread.daemon = True
            self._thread.start()
        if self.network_camera:
            self.network_camera.start()

    def stop(self):
        with self._lock:
            self._stop_event.set()
            self._generation += 1
            self.raw_buffer.invalidate()
            self.buffer.invalidate()
            self._last_status["camera"]["connected"] = False
            self._last_status.update(health="stopped", fps=0.0)
            self.events.offline("Runtime stopped")
        if self.network_camera:
            self.network_camera.stop()
        self.events.close()
        thread = self._thread
        if thread:
            thread.join(timeout=3.0)
        if self._capture_thread:
            self._capture_thread.join(timeout=3.0)

    def get_config(self):
        with self._lock:
            return json.loads(json.dumps(self.config))

    def update_config(self, update):
        with self._update_lock:
            return self._update_config(update)

    def _update_config(self, update):
        # Validate and persist before replacing the live configuration.
        with self._lock:
            previous = self.config
            candidate = merge_config(self.config, update)
            if self.config_path:
                save_config(self.config_path, candidate)
            self.config = candidate
            source_changed = any(
                previous.get(key) != self.config.get(key)
                for key in ("camera_index", "camera_device", "source", "sample_video", "resolution", "camera_fps", "camera_fourcc")
            )
            detector_changed = any(previous.get(key) != self.config.get(key) for key in ("model_path", "detector_backend"))
            if source_changed or detector_changed:
                self._generation += 1
                self.buffer.invalidate()
                self.events.offline("Camera or detector configuration changed")
            if source_changed:
                self.raw_buffer.invalidate()
            if detector_changed:
                self.detector = None
        if source_changed:
            with self._capture_lock:
                if self.frame_source:
                    self.frame_source.close()
                    self.frame_source = None
        if self.network_camera:
            self.network_camera.reconfigure(previous, candidate)
        return self.get_config()

    def status(self):
        with self._lock:
            status = json.loads(json.dumps(self._last_status))
            status["auto_snapshot"]["enabled"] = bool(self.config.get("auto_snapshot_enabled", False))
            status["auto_snapshot"]["label"] = self.config.get("auto_snapshot_label", "person")
            status["auto_snapshot"]["cooldown_seconds"] = self.config.get("auto_snapshot_cooldown_seconds", 30.0)
        metrics = read_system_metrics()
        status.update(metrics)
        if self.network_camera:
            status["network_camera"] = self.network_camera.status()
        if metrics.get("temperature_c") and metrics["temperature_c"] >= 78:
            status["health"] = "thermal_warning"
        return status

    def latest_detections(self):
        snapshot = self.buffer.snapshot()
        return {
            "frame_ts": snapshot["frame_ts"],
            "version": snapshot["version"],
            "detections": snapshot["detections"],
        }

    def wait_for_jpeg(self, last_version=None, timeout=1.0):
        return self.buffer.wait_for_jpeg(last_version, timeout)

    def save_snapshot(self, directory):
        os.makedirs(directory, exist_ok=True)
        snapshot = self.buffer.snapshot()
        if snapshot["jpeg"] is None:
            config = self.get_config()
            frame = placeholder_frame(
                config["resolution"]["width"], config["resolution"]["height"], "No frame available"
            )
            jpeg = encode_jpeg(frame, config["jpeg_quality"])
            detections = []
            frame_ts = time.time()
        else:
            jpeg = snapshot["jpeg"]
            detections = snapshot["detections"]
            frame_ts = snapshot["frame_ts"] or time.time()
        return self._write_snapshot(directory, "snapshot", "manual", jpeg, detections, frame_ts)

    def _capture_loop(self):
        try:
            self._capture_frames()
        finally:
            with self._capture_lock:
                if self.frame_source:
                    self.frame_source.close()
                    self.frame_source = None

    def _capture_frames(self):
        while not self._stop_event.is_set():
            paced_at = time.monotonic()
            with self._lock:
                config = self.get_config()
                generation = self._generation
            try:
                with self._capture_lock:
                    if self.frame_source is None:
                        self.frame_source = build_frame_source(config)
                        self.frame_source.open()
                    ok, frame = self.frame_source.read()
                if not ok:
                    raise CameraError("Frame source returned no frame.")
                with self._lock:
                    if generation != self._generation or self._stop_event.is_set():
                        continue
                    stamp = time.time()
                    self.raw_buffer.publish(frame, None, [], stamp, generation=generation)
                    self._last_status["camera"] = {"connected": True, "source": config["source"], "error": None}
                    self._last_status["last_frame_ts"] = stamp
            except Exception as exc:
                with self._lock:
                    if generation != self._generation or self._stop_event.is_set():
                        continue
                    self._generation += 1
                    self._record_error(str(exc))
                    self.events.offline("Camera unavailable")
                    self.raw_buffer.invalidate()
                    self._publish_placeholder(str(exc))
                with self._capture_lock:
                    if self.frame_source:
                        self.frame_source.close()
                        self.frame_source = None
                self._stop_event.wait(config.get("retry_interval_seconds", 2.0))
            interval = 1.0 / config.get("camera_fps", 30)
            self._stop_event.wait(max(0, interval - (time.monotonic() - paced_at)))

    def _run(self):
        version = None
        while not self._stop_event.is_set():
            item = self.raw_buffer.wait_for_frame(version, timeout=0.25)
            if item is None:
                continue
            version = item["version"]
            with self._lock:
                config = self.get_config()
                detector = self.detector
            started = time.monotonic()
            try:
                if detector is None:
                    candidate = build_detector(config)
                    with self._lock:
                        if self._stop_event.is_set() or item["generation"] != self._generation:
                            continue
                        self.detector = detector = candidate
                frame = item["frame"]
                detect_started = time.time()
                detections = detector.detect(frame.copy(), config)
                latency_ms = (time.time() - detect_started) * 1000.0
                overlay = draw_overlay(frame, detections)
                jpeg = encode_jpeg(overlay, config["jpeg_quality"])
                mock_fallback = (isinstance(detector, MockDetector) and config["detector_backend"] != "mock"
                                 and config["source"] != "synthetic")
                with self._lock:
                    if (self._stop_event.is_set() or item["generation"] != self._generation
                            or not self.raw_buffer.snapshot()["valid"]):
                        continue
                    self.buffer.publish(overlay, jpeg, detections, item["frame_ts"], generation=item["generation"])
                    self._record_success(len(detections), latency_ms)
                    if mock_fallback:
                        self.events.offline("Automatic mock fallback is not a live analytics source")
                    else:
                        self.events.observe(detections, frame_ts=item["frame_ts"], confidence=config["confidence"],
                                            allowlist=config["class_allowlist"])
                if not mock_fallback:
                    self._maybe_auto_snapshot(jpeg, detections, item["frame_ts"])
            except Exception as exc:
                with self._lock:
                    if self._stop_event.is_set() or item["generation"] != self._generation:
                        continue
                    self._last_status.update(health="error", fps=0.0, last_error=str(exc))
                    self._last_status["model"].update(loaded=False, error=str(exc))
                    self.events.offline("Detector unavailable")
                    self._publish_placeholder("Detector unavailable")
                    self.detector = None
                self._stop_event.wait(config.get("retry_interval_seconds", 2.0))
            limit = config.get("network_camera", {}).get("annotated_fps", 15)
            self._stop_event.wait(max(0, 1.0 / limit - (time.monotonic() - started)))

    def _record_success(self, detection_count, latency_ms):
        now = time.time()
        self._frames += 1
        elapsed = max(0.001, now - self._fps_window_started)
        fps = self._frames / elapsed
        if elapsed >= 5.0:
            self._frames = 0
            self._fps_window_started = now
        with self._lock:
            self._last_status.update(
                {
                    "camera": {"connected": True, "source": self.config.get("source"), "error": None},
                    "model": {
                        "backend": getattr(self.detector, "backend_name", "unknown"),
                        "path": self.config.get("model_path"),
                        "loaded": True,
                        "error": None,
                    },
                    "health": "running",
                    "fps": round(fps, 2),
                    "latency_ms": round(latency_ms, 1),
                    "detection_count": int(detection_count),
                    "last_error": None,
                    "last_frame_ts": now,
                }
            )

    def _record_error(self, message):
        with self._lock:
            self._last_status.update(
                {
                    "camera": {"connected": False, "source": self.config.get("source"), "error": message},
                    "health": "error",
                    "fps": 0.0,
                    "latency_ms": None,
                    "detection_count": 0,
                    "last_error": message,
                    "last_frame_ts": time.time(),
                }
            )

    def _publish_placeholder(self, message):
        config = self.get_config()
        frame = placeholder_frame(config["resolution"]["width"], config["resolution"]["height"], message[:72])
        jpeg = encode_jpeg(frame, config["jpeg_quality"])
        self.buffer.publish(frame, jpeg, [], time.time(), valid=False)

    def _maybe_auto_snapshot(self, jpeg, detections, frame_ts, now=None):
        config = self.get_config()
        if not config.get("auto_snapshot_enabled", False):
            return None
        label = config.get("auto_snapshot_label", "person").strip().lower()
        if not label:
            return None
        if not any((item.get("label") or "").lower() == label for item in detections):
            return None

        now = time.monotonic() if now is None else float(now)
        cooldown = float(config.get("auto_snapshot_cooldown_seconds", 30.0))
        if self._last_auto_snapshot_attempt_at is not None and now - self._last_auto_snapshot_attempt_at < cooldown:
            return None
        self._last_auto_snapshot_attempt_at = now

        try:
            directory = _capture_dir()
            result = self._write_snapshot(directory, "auto-%s" % label.replace(" ", "-"), "auto", jpeg, detections, frame_ts)
        except Exception as exc:
            with self._lock:
                self._last_status["auto_snapshot"]["last_error"] = str(exc)
            return None

        self._auto_snapshot_count += 1
        with self._lock:
            self._last_status["auto_snapshot"].update(
                {
                    "count": self._auto_snapshot_count,
                    "last_trigger_ts": frame_ts,
                    "last_image_path": result["image_path"],
                    "last_metadata_path": result["metadata_path"],
                    "last_error": None,
                }
            )
        return result

    def _write_snapshot(self, directory, prefix, snapshot_type, jpeg, detections, frame_ts):
        os.makedirs(directory, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(frame_ts))
        image_path, json_path = _snapshot_paths(directory, prefix, stamp)
        with open(image_path, "wb") as handle:
            handle.write(jpeg)
        with open(json_path, "w") as handle:
            json.dump(
                {"frame_ts": frame_ts, "snapshot_type": snapshot_type, "detections": detections},
                handle,
                indent=2,
                sort_keys=True,
            )
            handle.write("\n")
        return {"image_path": image_path, "metadata_path": json_path, "detections": detections}

    def _initial_status(self):
        return {
            "health": "starting",
            "camera": {"connected": False, "source": self.config.get("source"), "error": None},
            "model": {
                "backend": self.config.get("detector_backend"),
                "path": self.config.get("model_path"),
                "loaded": False,
                "error": None,
            },
            "fps": 0.0,
            "latency_ms": None,
            "detection_count": 0,
            "dropped_frames": 0,
            "last_error": None,
            "last_frame_ts": None,
            "temperature_c": None,
            "memory": None,
            "auto_snapshot": {
                "enabled": bool(self.config.get("auto_snapshot_enabled", False)),
                "label": self.config.get("auto_snapshot_label", "person"),
                "cooldown_seconds": self.config.get("auto_snapshot_cooldown_seconds", 30.0),
                "count": 0,
                "last_trigger_ts": None,
                "last_image_path": None,
                "last_metadata_path": None,
                "last_error": None,
            },
        }


def mjpeg_stream(runtime):
    last_version = None
    while True:
        item = runtime.wait_for_jpeg(last_version=last_version, timeout=1.0)
        if item is None:
            config = runtime.get_config()
            jpeg = encode_jpeg(
                placeholder_frame(config["resolution"]["width"], config["resolution"]["height"], "Waiting for camera"),
                config["jpeg_quality"],
            )
        else:
            last_version = item["version"]
            jpeg = item["jpeg"]
        yield b"--frame\r\n"
        yield b"Content-Type: image/jpeg\r\n"
        yield b"Content-Length: " + str(len(jpeg)).encode("ascii") + b"\r\n\r\n"
        yield jpeg
        yield b"\r\n"


def _capture_dir():
    return os.environ.get("CYBERVISUAL_CAPTURE_DIR", os.path.abspath("captures"))


def _snapshot_paths(directory, prefix, stamp):
    safe_prefix = "".join(char if char.isalnum() or char in ("-", "_") else "-" for char in prefix).strip("-")
    safe_prefix = safe_prefix or "snapshot"
    image_path = os.path.join(directory, "%s-%s.jpg" % (safe_prefix, stamp))
    json_path = os.path.join(directory, "%s-%s.json" % (safe_prefix, stamp))
    index = 1
    while os.path.exists(image_path) or os.path.exists(json_path):
        image_path = os.path.join(directory, "%s-%s-%03d.jpg" % (safe_prefix, stamp, index))
        json_path = os.path.join(directory, "%s-%s-%03d.json" % (safe_prefix, stamp, index))
        index += 1
    return image_path, json_path
