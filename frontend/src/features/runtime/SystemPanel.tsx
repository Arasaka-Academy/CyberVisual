import { Cpu } from "lucide-react";

import type { RuntimeConfig } from "../settings/types";
import type { RuntimeStatus } from "./types";

export function SystemPanel({ status, config }: { status: RuntimeStatus; config: RuntimeConfig }) {
  return (
    <section className="panel system-panel">
      <div className="panel-heading">
        <div>
          <h2>System</h2>
          <p>{status.model.loaded ? status.model.path : "Model pending"}</p>
        </div>
        <Cpu size={18} aria-hidden="true" />
      </div>
      <dl className="system-list">
        <div><dt>Detector</dt><dd>{status.model.backend}</dd></div>
        <div><dt>Auto Snap</dt><dd>{status.auto_snapshot.enabled ? `${status.auto_snapshot.count} saved` : "Off"}</dd></div>
        <div><dt>Threshold</dt><dd>{Math.round(config.confidence * 100)}%</dd></div>
        <div><dt>IOU</dt><dd>{Math.round(config.iou * 100)}%</dd></div>
        <div><dt>Dropped</dt><dd>{status.dropped_frames}</dd></div>
      </dl>
    </section>
  );
}
