import { CameraOff, ScanLine } from "lucide-react";

import type { RuntimeStatus } from "../runtime/types";
import type { RuntimeConfig } from "../settings/types";

export function StreamPreview({ status, resolution, streamUrl, streamError, onLoad, onError }: {
  status: RuntimeStatus;
  resolution: RuntimeConfig["resolution"];
  streamUrl: string;
  streamError: boolean;
  onLoad: () => void;
  onError: () => void;
}) {
  return (
    <div className="video-stage">
      {!streamError ? (
        <img
          className="video-stream"
          src={streamUrl}
          alt="Live YOLO detection stream"
          onLoad={onLoad}
          onError={onError}
        />
      ) : (
        <div className="stream-placeholder" role="status">
          <CameraOff size={44} />
          <span>Stream offline</span>
        </div>
      )}
      <div className="video-hud top-left">
        <span className={`live-dot ${status.camera.connected ? "on" : "off"}`} />
        <span>{status.camera.connected ? "LIVE" : "CAMERA OFFLINE"}</span>
      </div>
      <div className="video-tech-tag">
        <ScanLine size={14} aria-hidden="true" />
        <span>CYBERVISUAL</span>
        <strong>{status.model.loaded ? "MODEL READY" : "LOADING"}</strong>
      </div>
      <div className="compute-rail" aria-hidden="true">
        <span>NVIDIA CUDA</span>
        <i />
        <span>TENSORRT</span>
      </div>
      <div className="video-hud bottom-right">
        <span>{resolution.width}x{resolution.height}</span>
        <span>{status.model.backend}</span>
      </div>
      <div className="target-frame" aria-hidden="true">
        <span className="frame-corner top-left" />
        <span className="frame-corner top-right" />
        <span className="frame-corner bottom-left" />
        <span className="frame-corner bottom-right" />
      </div>
      <div className="video-scanline" aria-hidden="true" />
    </div>
  );
}
