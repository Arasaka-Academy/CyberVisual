import type { ReactNode } from "react";
import { Activity, Gauge } from "lucide-react";

import type { RuntimeStatus } from "./types";

export function RuntimeStatusBar({ status }: { status: RuntimeStatus }) {
  const healthTone = status.health === "running" ? "ok" : status.health === "thermal_warning" ? "warn" : "bad";
  return (
    <>
      <StatusPill tone={healthTone} label={labelForHealth(status.health)} />
      <MetricChip icon={<Activity size={16} />} label="FPS" value={formatNumber(status.fps, 1)} />
      <MetricChip icon={<Gauge size={16} />} label="Latency" value={formatLatency(status.latency_ms)} />
    </>
  );
}

function StatusPill({ tone, label }: { tone: "ok" | "warn" | "bad"; label: string }) {
  return (
    <div className={`status-pill ${tone}`}>
      <span />
      {label}
    </div>
  );
}

function MetricChip({ icon, label, value }: { icon: ReactNode; label: string; value: string }) {
  return (
    <div className="metric-chip">
      {icon}
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function formatLatency(latency: number | null) {
  return latency == null ? "N/A" : `${Math.round(latency)} ms`;
}

function formatNumber(value: number, digits: number) {
  return Number.isFinite(value) ? value.toFixed(digits) : "0.0";
}

function labelForHealth(health: string) {
  if (health === "running") return "RUNNING";
  if (health === "thermal_warning") return "THERMAL";
  if (health === "starting") return "STARTING";
  return "ERROR";
}
