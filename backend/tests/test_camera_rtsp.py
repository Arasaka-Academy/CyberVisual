import queue
import threading
from types import SimpleNamespace

import numpy as np

from cybervisual.config import DEFAULT_CONFIG
from cybervisual.network_camera.rtsp import RTSPServer
from cybervisual.runtime import RuntimeService


def test_rtsp_timestamps_keep_advancing_after_utc_moves_backwards():
    pushed = queue.Queue()

    class Buffer:
        @staticmethod
        def new_allocate(*args):
            return Buffer()

        def fill(self, *args):
            pass

    class Source:
        def emit(self, signal, buffer=None):
            if signal == "push-buffer":
                pushed.put(buffer.pts)
            return 0

    runtime = RuntimeService(config=dict(DEFAULT_CONFIG))
    server = RTSPServer(runtime, runtime.get_config()["network_camera"], None)
    server.Gst = SimpleNamespace(Buffer=Buffer, SECOND=1000000000, FlowReturn=SimpleNamespace(OK=0))
    session = {"profile": "raw", "stop": threading.Event(), "demand": threading.Event(), "media": SimpleNamespace()}
    session["demand"].set()
    worker = threading.Thread(target=server._feed, args=(Source(), session))
    worker.start()
    try:
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        timestamps = []
        for utc in (1000.0, 1000.1, 940.0):
            runtime.raw_buffer.publish(frame, None, [], utc)
            timestamps.append(pushed.get(timeout=1))
        assert timestamps[2] - timestamps[1] >= server.Gst.SECOND // 60
    finally:
        session["stop"].set()
        worker.join(timeout=1)
        assert not worker.is_alive()
