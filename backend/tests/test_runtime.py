import json
import os
import time
import threading

import numpy as np

from cybervisual.detector import BaseDetector, MockDetector
from cybervisual.config import DEFAULT_CONFIG
from cybervisual.runtime import RuntimeService


PERSON_DETECTION = {
    "label": "person",
    "confidence": 0.91,
    "bbox": {"x1": 1, "y1": 2, "x2": 20, "y2": 40},
    "frame_ts": 100.0,
}


def test_auto_snapshot_writes_person_capture(tmp_path, monkeypatch):
    monkeypatch.setenv("CYBERVISUAL_CAPTURE_DIR", str(tmp_path))
    runtime = RuntimeService(config=dict(DEFAULT_CONFIG, auto_snapshot_enabled=True))

    result = runtime._maybe_auto_snapshot(b"\xff\xd8\xff\xd9", [PERSON_DETECTION], 100.0, now=100.0)

    assert result is not None
    assert os.path.exists(result["image_path"])
    assert os.path.exists(result["metadata_path"])
    assert os.path.basename(result["image_path"]).startswith("auto-person-")
    metadata = json.loads(open(result["metadata_path"]).read())
    assert metadata["snapshot_type"] == "auto"
    assert metadata["detections"][0]["label"] == "person"
    status = runtime.status()
    assert status["auto_snapshot"]["count"] == 1
    assert status["auto_snapshot"]["last_image_path"] == result["image_path"]


def test_auto_snapshot_ignores_non_person(tmp_path, monkeypatch):
    monkeypatch.setenv("CYBERVISUAL_CAPTURE_DIR", str(tmp_path))
    runtime = RuntimeService(config=dict(DEFAULT_CONFIG, auto_snapshot_enabled=True))

    result = runtime._maybe_auto_snapshot(
        b"\xff\xd8\xff\xd9",
        [dict(PERSON_DETECTION, label="laptop")],
        100.0,
        now=100.0,
    )

    assert result is None
    assert list(tmp_path.iterdir()) == []


def test_auto_snapshot_can_be_disabled(tmp_path, monkeypatch):
    monkeypatch.setenv("CYBERVISUAL_CAPTURE_DIR", str(tmp_path))
    runtime = RuntimeService(config=dict(DEFAULT_CONFIG, auto_snapshot_enabled=False))

    result = runtime._maybe_auto_snapshot(b"\xff\xd8\xff\xd9", [PERSON_DETECTION], 100.0, now=100.0)

    assert result is None
    assert list(tmp_path.iterdir()) == []


def test_auto_snapshot_uses_configured_label_and_case_insensitive_matching(tmp_path, monkeypatch):
    monkeypatch.setenv("CYBERVISUAL_CAPTURE_DIR", str(tmp_path))
    runtime = RuntimeService(
        config=dict(DEFAULT_CONFIG, auto_snapshot_enabled=True, auto_snapshot_label="Laptop")
    )

    result = runtime._maybe_auto_snapshot(
        b"\xff\xd8\xff\xd9",
        [dict(PERSON_DETECTION, label="laptop")],
        100.0,
        now=100.0,
    )

    assert result is not None
    assert os.path.basename(result["image_path"]).startswith("auto-laptop-")


def test_auto_snapshot_respects_cooldown(tmp_path, monkeypatch):
    monkeypatch.setenv("CYBERVISUAL_CAPTURE_DIR", str(tmp_path))
    runtime = RuntimeService(
        config=dict(DEFAULT_CONFIG, auto_snapshot_enabled=True, auto_snapshot_cooldown_seconds=30.0)
    )

    first = runtime._maybe_auto_snapshot(b"\xff\xd8\xff\xd9", [PERSON_DETECTION], 100.0, now=100.0)
    second = runtime._maybe_auto_snapshot(b"\xff\xd8\xff\xd9", [PERSON_DETECTION], 105.0, now=105.0)

    assert first is not None
    assert second is None
    assert len(list(tmp_path.glob("*.jpg"))) == 1


def test_auto_snapshot_failure_respects_cooldown(monkeypatch):
    runtime = RuntimeService(
        config=dict(DEFAULT_CONFIG, auto_snapshot_enabled=True, auto_snapshot_cooldown_seconds=30.0)
    )
    calls = []

    def fail_write(*args):
        calls.append(args)
        raise OSError("disk unavailable")

    monkeypatch.setattr(runtime, "_write_snapshot", fail_write)

    first = runtime._maybe_auto_snapshot(b"\xff\xd8\xff\xd9", [PERSON_DETECTION], 100.0, now=100.0)
    second = runtime._maybe_auto_snapshot(b"\xff\xd8\xff\xd9", [PERSON_DETECTION], 105.0, now=105.0)

    assert first is None
    assert second is None
    assert len(calls) == 1
    assert runtime.status()["auto_snapshot"]["last_error"] == "disk unavailable"


def test_runtime_loop_triggers_auto_snapshot(tmp_path, monkeypatch):
    monkeypatch.setenv("CYBERVISUAL_CAPTURE_DIR", str(tmp_path))
    runtime = RuntimeService(
        config=dict(DEFAULT_CONFIG, auto_snapshot_enabled=True, auto_snapshot_cooldown_seconds=30.0),
        frame_source=FakeFrameSource(),
        detector=PersonDetector(),
    )

    runtime.start()
    try:
        deadline = time.time() + 2.0
        while time.time() < deadline and not list(tmp_path.glob("auto-person-*.jpg")):
            time.sleep(0.02)
    finally:
        runtime.stop()

    captures = list(tmp_path.glob("auto-person-*.jpg"))
    assert len(captures) == 1
    assert runtime.status()["auto_snapshot"]["count"] == 1


def test_manual_snapshot_metadata_marks_manual(tmp_path):
    runtime = RuntimeService(config=dict(DEFAULT_CONFIG, auto_snapshot_enabled=True))

    result = runtime.save_snapshot(str(tmp_path))

    metadata = json.loads(open(result["metadata_path"]).read())
    assert metadata["snapshot_type"] == "manual"


def test_success_status_clears_previous_error():
    runtime = RuntimeService(config=dict(DEFAULT_CONFIG))
    runtime._record_error("temporary failure")

    runtime._record_success(1, 12.3)

    assert runtime.status()["last_error"] is None


class FakeFrameSource(object):
    def read(self):
        return True, np.zeros((32, 32, 3), dtype=np.uint8)

    def close(self):
        pass


class PersonDetector(BaseDetector):
    backend_name = "fake"

    def detect(self, frame, config):
        return [PERSON_DETECTION]


def test_slow_inference_does_not_block_raw_capture(tmp_path, monkeypatch):
    monkeypatch.setenv("CYBERVISUAL_CAPTURE_DIR", str(tmp_path))
    entered, release = threading.Event(), threading.Event()

    class SlowDetector(BaseDetector):
        def detect(self, frame, config):
            entered.set()
            release.wait(2)
            return []

    runtime = RuntimeService(config=dict(DEFAULT_CONFIG, auto_snapshot_enabled=False),
                             frame_source=FakeFrameSource(), detector=SlowDetector())
    runtime.start()
    try:
        assert entered.wait(1)
        version = runtime.raw_buffer.snapshot()["version"]
        deadline = time.monotonic() + 1
        while time.monotonic() < deadline and runtime.raw_buffer.snapshot()["version"] <= version + 2:
            time.sleep(0.01)
        assert runtime.raw_buffer.snapshot()["version"] > version + 2
    finally:
        release.set()
        runtime.stop()


def test_capture_failure_discards_inference_finishing_after_disconnect(monkeypatch):
    from cybervisual import runtime as module

    encoding, release, disconnected = threading.Event(), threading.Event(), threading.Event()
    original_encode = module.encode_jpeg

    def slow_encode(frame, quality):
        if threading.current_thread().name == "cybervisual-runtime":
            encoding.set()
            release.wait(2)
        return original_encode(frame, quality)

    class DisconnectingSource(FakeFrameSource):
        def read(self):
            if disconnected.is_set():
                raise RuntimeError("Camera disconnected")
            return super().read()

    monkeypatch.setattr(module, "encode_jpeg", slow_encode)
    runtime = RuntimeService(config=dict(DEFAULT_CONFIG, retry_interval_seconds=3, auto_snapshot_enabled=False),
                             frame_source=DisconnectingSource(), detector=PersonDetector())
    runtime.start()
    try:
        assert encoding.wait(1)
        disconnected.set()
        deadline = time.monotonic() + 1
        while time.monotonic() < deadline and runtime.raw_buffer.snapshot()["valid"]:
            time.sleep(0.01)
        assert not runtime.raw_buffer.snapshot()["valid"]
        release.set()
        time.sleep(0.15)
        assert not runtime.buffer.snapshot()["valid"]
        assert not runtime.events.status()["online"]
        assert not runtime.events.status()["presence"]["person"]
    finally:
        release.set()
        runtime.stop()


def test_automatic_mock_fallback_on_real_camera_does_not_publish_ai_events():
    class CameraSource(FakeFrameSource):
        def read(self):
            return True, np.zeros((240, 320, 3), dtype=np.uint8)

    runtime = RuntimeService(config=dict(DEFAULT_CONFIG, source="camera", detector_backend="auto",
                                         auto_snapshot_enabled=False),
                             frame_source=CameraSource(), detector=MockDetector())
    runtime.start()
    try:
        assert runtime.buffer.wait_for_frame(timeout=1)
        events = runtime.events.status()
        assert not events["online"]
        assert not events["presence"]["person"]
        assert "mock" in events["last_error"].lower()
    finally:
        runtime.stop()


def test_stop_marks_camera_offline_and_invalidates_stream_buffers():
    runtime = RuntimeService(config=dict(DEFAULT_CONFIG, auto_snapshot_enabled=False),
                             frame_source=FakeFrameSource(), detector=PersonDetector())
    runtime.start()
    assert runtime.buffer.wait_for_frame(timeout=1)
    runtime.stop()
    assert not runtime.status()["camera"]["connected"]
    assert not runtime.raw_buffer.snapshot()["valid"]
    assert not runtime.buffer.snapshot()["valid"]


def test_model_change_during_loading_cannot_install_previous_detector(monkeypatch):
    loading, release = threading.Event(), threading.Event()
    calls = []

    def build(config):
        calls.append(config["model_path"])
        if len(calls) == 1:
            loading.set()
            release.wait(2)
        return PersonDetector()

    monkeypatch.setattr("cybervisual.runtime.build_detector", build)
    runtime = RuntimeService(config=dict(DEFAULT_CONFIG, auto_snapshot_enabled=False), frame_source=FakeFrameSource())
    runtime.start()
    try:
        assert loading.wait(1)
        runtime.update_config({"model_path": "replacement.engine"})
        release.set()
        deadline = time.monotonic() + 1
        while time.monotonic() < deadline and len(calls) < 2:
            time.sleep(0.01)
        assert calls == [DEFAULT_CONFIG["model_path"], "replacement.engine"]
    finally:
        release.set()
        runtime.stop()
