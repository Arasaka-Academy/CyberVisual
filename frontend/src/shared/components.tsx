import { useRef, useState } from "react";
import type { ReactNode } from "react";
import { AlertCircle, ChevronRight, Copy, RefreshCw } from "lucide-react";

export type Tone = "good" | "warn" | "bad" | "neutral";
export function Badge({
  children,
  tone = "neutral",
}: {
  children: ReactNode;
  tone?: Tone;
}) {
  return (
    <span className={`badge ${tone}`}>
      <span className="status-dot" aria-hidden="true" />
      {children}
    </span>
  );
}
export function Panel({
  title,
  description,
  action,
  children,
  className = "",
}: {
  title: string;
  description?: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`panel ${className}`}>
      <div className="panel-heading">
        <div>
          <h2>{title}</h2>
          {description && <p>{description}</p>}
        </div>
        {action}
      </div>
      {children}
    </section>
  );
}
export function Notice({
  children,
  tone = "bad",
  retry,
}: {
  children: ReactNode;
  tone?: Tone;
  retry?: () => void;
}) {
  return (
    <div
      className={`notice ${tone}`}
      role={tone === "bad" ? "alert" : "status"}
    >
      <AlertCircle size={18} aria-hidden="true" />
      <div>{children}</div>
      {retry && (
        <button type="button" className="button small" onClick={retry}>
          <RefreshCw size={14} aria-hidden="true" />
          重试
        </button>
      )}
    </div>
  );
}
export function Empty({
  title,
  children,
}: {
  title: string;
  children?: ReactNode;
}) {
  return (
    <div className="empty-state">
      <strong>{title}</strong>
      {children && <p>{children}</p>}
    </div>
  );
}
export function Field({
  label,
  help,
  children,
}: {
  label: string;
  help?: string;
  children: ReactNode;
}) {
  return (
    <label className="field">
      <span>{label}</span>
      {children}
      {help && <small>{help}</small>}
    </label>
  );
}
export function Toggle({
  label,
  help,
  checked,
  onChange,
  disabled = false,
}: {
  label: string;
  help?: string;
  checked: boolean;
  disabled?: boolean;
  onChange: (value: boolean) => void;
}) {
  return (
    <label className="toggle-row">
      <span>
        <strong>{label}</strong>
        {help && <small>{help}</small>}
      </span>
      <input
        type="checkbox"
        checked={checked}
        disabled={disabled}
        onChange={(event) => onChange(event.target.checked)}
      />
      <span className="toggle-track" aria-hidden="true" />
    </label>
  );
}
export function CopyField({
  label,
  value,
}: {
  label: string;
  value: string | null | undefined;
}) {
  const ref = useRef<HTMLInputElement>(null);
  const [message, setMessage] = useState("");
  return (
    <div className="copy-field">
      <label>
        {label}
        <div>
          <input
            ref={ref}
            value={value || "暂不可用"}
            readOnly
            onFocus={(event) => event.currentTarget.select()}
          />
          <button
            type="button"
            className="button icon"
            aria-label={`复制${label}`}
            disabled={!value}
            onClick={async () => {
              try {
                if (!navigator.clipboard?.writeText) throw new Error();
                await navigator.clipboard.writeText(value!);
                setMessage("已复制");
              } catch {
                ref.current?.focus();
                ref.current?.select();
                setMessage("地址已选中，请手动复制。");
              }
            }}
          >
            <Copy size={16} aria-hidden="true" />
          </button>
        </div>
      </label>
      {message && <small role="status">{message}</small>}
    </div>
  );
}
export function LinkAction({
  to,
  children,
}: {
  to: string;
  children: ReactNode;
}) {
  return (
    <a className="text-link" href={to}>
      {children}
      <ChevronRight size={15} aria-hidden="true" />
    </a>
  );
}
export function timeText(value: number | null | undefined, seconds = false) {
  return value
    ? new Intl.DateTimeFormat("zh-CN", {
        hour: "2-digit",
        minute: "2-digit",
        ...(seconds ? { second: "2-digit" } : {}),
      }).format(new Date(value))
    : "尚未更新";
}
export function Freshness({
  updatedAt,
  now,
  error = false,
}: {
  updatedAt: number | null;
  now: number;
  error?: boolean;
}) {
  const stale = updatedAt !== null && now - updatedAt > 5000;
  return (
    <span className={`freshness ${stale || error ? "stale" : ""}`}>
      {!updatedAt
        ? "等待设备数据"
        : `${stale ? "数据已过期 · " : error ? "更新失败 · " : "更新于 "}${timeText(updatedAt, true)}`}
    </span>
  );
}
export const stateLabel = (state?: string) =>
  ({
    running: "运行中",
    starting: "启动中",
    stopped: "已停止",
    disabled: "未启用",
    unavailable: "不可用",
    degraded: "部分异常",
    error: "故障",
  })[state || ""] || "未知";
export const stateTone = (state?: string): Tone =>
  state === "running"
    ? "good"
    : state === "error" || state === "unavailable"
      ? "bad"
      : state === "degraded" || state === "starting"
        ? "warn"
        : "neutral";
