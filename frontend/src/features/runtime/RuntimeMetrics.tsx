import type { ReactNode } from "react";
import { Camera, HardDrive, Thermometer, Zap } from "lucide-react";

import type { RuntimeStatus } from "./types";

export function RuntimeMetrics({ status }: { status: RuntimeStatus }) {
  return (
    <div className="metrics-grid" aria-label="Runtime metrics">
      <MetricPanel channel="CAM 01" icon={<Camera size={18} />} label="Camera" value={status.camera.connected ? status.camera.source : "Offline"} tone={status.camera.connected ? "ok" : "bad"} />
      <MetricPanel channel="AI 02" icon={<Zap size={18} />} label="Detections" value={String(status.detection_count)} tone="ok" />
      <MetricPanel channel="TMP 03" icon={<Thermometer size={18} />} label="Thermal" value={status.temperature_c == null ? "N/A" : `${status.temperature_c.toFixed(1)} C`} tone={status.health === "thermal_warning" ? "warn" : "neutral"} />
      <MetricPanel channel="MEM 04" icon={<HardDrive size={18} />} label="Memory" value={status.memory ? `${status.memory.percent.toFixed(1)}%` : "N/A"} tone="neutral" />
    </div>
  );
}

function MetricPanel({
  channel,
  icon,
  label,
  value,
  tone
}: {
  channel: string;
  icon: ReactNode;
  label: string;
  value: string;
  tone: "ok" | "warn" | "bad" | "neutral";
}) {
  return (
    <article className={`metric-panel ${tone}`} data-channel={channel}>
      <div>{icon}</div>
      <span>{label}</span>
      <strong>{value}</strong>
    </article>
  );
}
