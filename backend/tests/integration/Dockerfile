ARG BASE_IMAGE=debian:bookworm-slim
FROM ${BASE_IMAGE}
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-venv python3-gi python3-gst-1.0 \
    gir1.2-gst-rtsp-server-1.0 gstreamer1.0-plugins-base \
    gstreamer1.0-plugins-good gstreamer1.0-plugins-bad \
    gstreamer1.0-plugins-ugly ffmpeg ca-certificates \
    && rm -rf /var/lib/apt/lists/*
RUN python3 -m venv --system-site-packages /opt/venv
ENV PATH="/opt/venv/bin:${PATH}" PYTHONPATH=/workspace/backend
COPY backend/requirements*.txt /tmp/requirements/
ARG PIP_INDEX_URL=https://pypi.org/simple
RUN pip install --no-cache-dir --timeout 120 --retries 5 \
    --index-url "${PIP_INDEX_URL}" -r /tmp/requirements/requirements-integration.txt
WORKDIR /workspace/backend
CMD ["python", "-m", "pytest", "tests", "-q"]
