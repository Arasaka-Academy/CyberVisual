import { useEffect, useState } from "react";
import {
  Camera,
  CameraOff,
  Maximize2,
  Pause,
  Play,
  RefreshCw,
} from "lucide-react";
import { API_BASE } from "../../shared/api";
import { captureSnapshot, getLatestDetections } from "../detections/api";
import {
  Badge,
  Empty,
  Freshness,
  Notice,
  Panel,
} from "../../shared/components";
import { errorMessage, usePoll } from "../../shared/hooks";
import type { RuntimeStatus } from "../runtime/types";
import PTZPanel from "../ptz/PTZPanel";

export default function Monitor({
  status,
  visible,
  now,
  stale,
}: {
  status: RuntimeStatus | null;
  visible: boolean;
  now: number;
  stale: boolean;
}) {
  const detections = usePoll(getLatestDetections, 1000, visible);
  const [paused, setPaused] = useState(false);
  const [streamError, setStreamError] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [streamKey, setStreamKey] = useState(0);
  const [saving, setSaving] = useState(false);
  const [snapshotError, setSnapshotError] = useState("");
  const [notice, setNotice] = useState("");
  const frameFresh =
    !!status?.last_frame_ts && now - status.last_frame_ts * 1000 <= 5000;
  const live =
    !stale &&
    !!status?.camera.connected &&
    frameFresh &&
    !streamError &&
    loaded &&
    !paused &&
    visible;
  useEffect(() => {
    if (!visible) setLoaded(false);
  }, [visible]);
  const reconnect = () => {
    setStreamError(false);
    setLoaded(false);
    setPaused(false);
    setStreamKey((value) => value + 1);
  };
  const save = async () => {
    if (saving) return;
    setSaving(true);
    setSnapshotError("");
    setNotice("");
    try {
      const result = await captureSnapshot();
      setNotice(`快照已保存到设备：${result.image_path}`);
    } catch (failure) {
      setSnapshotError(errorMessage(failure));
    } finally {
      setSaving(false);
    }
  };
  return (
    <div className="monitor-grid">
      <Panel
        title="实时画面"
        description={`AI 标注预览 · MJPEG${status?.camera.source === "synthetic" ? " · 合成测试源" : status?.camera.source === "video" ? " · 本地视频" : ""}${status?.model.backend === "mock" ? " · 模拟检测" : ""}`}
        action={
          <Badge tone={live ? "good" : "neutral"}>
            {paused ? "预览已暂停" : live ? "实时" : "等待画面"}
          </Badge>
        }
        className="video-panel"
      >
        <div className="video-stage">
          {!paused && visible && !streamError ? (
            <>
              <img
                key={streamKey}
                src={`${API_BASE}/stream.mjpg?view=${streamKey}`}
                alt="摄像头 AI 标注实时画面"
                onLoad={() => setLoaded(true)}
                onError={() => {
                  setStreamError(true);
                  setLoaded(false);
                }}
              />
              {!loaded && (
                <div className="video-loading">
                  <span className="loading-dot" />
                  正在连接视频源…
                </div>
              )}
            </>
          ) : (
            <div className="stream-placeholder">
              <CameraOff size={38} aria-hidden="true" />
              <strong>
                {paused
                  ? "预览已暂停"
                  : !visible
                    ? "页面隐藏，预览已暂停"
                    : "预览连接中断"}
              </strong>
              <span>设备视频输出与 AI 服务独立运行。</span>
              {streamError && (
                <button className="button" onClick={reconnect}>
                  <RefreshCw size={16} aria-hidden="true" />
                  重新连接
                </button>
              )}
            </div>
          )}
        </div>
        <div className="video-toolbar">
          <div className="button-row wrap">
            <button
              type="button"
              className="button"
              onClick={() => {
                if (paused) reconnect();
                else {
                  setPaused(true);
                  setLoaded(false);
                }
              }}
            >
              {paused ? (
                <Play size={16} aria-hidden="true" />
              ) : (
                <Pause size={16} aria-hidden="true" />
              )}
              {paused ? "恢复预览" : "暂停预览"}
            </button>
            <button type="button" className="button" onClick={reconnect}>
              <RefreshCw size={16} aria-hidden="true" />
              重连
            </button>
            <button
              type="button"
              className="button"
              disabled={saving || !frameFresh}
              onClick={() => void save()}
            >
              <Camera size={16} aria-hidden="true" />
              {saving ? "保存中…" : "保存快照"}
            </button>
          </div>
          <button
            type="button"
            className="button icon"
            aria-label="全屏预览"
            onClick={(event) => {
              const stage = event.currentTarget
                .closest(".video-panel")
                ?.querySelector(".video-stage");
              void stage
                ?.requestFullscreen?.()
                .catch(() => setSnapshotError("当前浏览器无法进入全屏预览。"));
            }}
          >
            <Maximize2 size={17} aria-hidden="true" />
          </button>
        </div>
        {snapshotError && <Notice>{snapshotError}</Notice>}
        {notice && (
          <p className="save-notice path-notice" role="status">
            {notice}
          </p>
        )}
        {status?.camera.error && <Notice>{status.camera.error}</Notice>}
        {status?.model.error && <Notice>{status.model.error}</Notice>}
      </Panel>
      <PTZPanel visible={visible} now={now} />
      <Panel
        className="detections-panel"
        title="当前检测"
        description="当前推理帧中的目标，不代表事件累计次数"
        action={
          <Freshness
            updatedAt={detections.updatedAt}
            now={now}
            error={!!detections.error}
          />
        }
      >
        {detections.error && (
          <Notice retry={detections.refresh}>{detections.error}</Notice>
        )}
        {!detections.data ? (
          <Empty title="正在读取检测结果…" />
        ) : !detections.data.detections.length ? (
          <Empty title="当前帧未检出目标">
            检测结果受置信度阈值与类别过滤设置影响。
          </Empty>
        ) : (
          <div className="detection-grid">
            {detections.data.detections.map((detection, index) => (
              <div
                className="detection-item"
                key={`${detection.label}-${index}`}
              >
                <span className="detection-icon">
                  <Camera size={16} aria-hidden="true" />
                </span>
                <div>
                  <strong>{detection.label}</strong>
                  <small>目标 {String(index + 1).padStart(2, "0")}</small>
                </div>
                <span className="confidence">
                  {Math.round(detection.confidence * 100)}%
                </span>
              </div>
            ))}
          </div>
        )}
        {detections.data?.frame_ts &&
        now - detections.data.frame_ts * 1000 > 5000 ? (
          <p className="form-warning">检测帧已过期，以上为最近一次结果。</p>
        ) : null}
      </Panel>
    </div>
  );
}
