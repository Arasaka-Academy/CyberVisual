import { useRef, useState } from "react";
import type { ReactNode } from "react";
import { ChevronRight, Copy, RefreshCw } from "lucide-react";
import { Badge as CyberBadge } from "../components/cyberui/badge";
import { Panel as CyberPanel, type PanelShape } from "../components/cyberui/panel";
import { Alert } from "../components/cyberui/alert";
import { EmptyState } from "../components/cyberui/empty-state";
import { Field as CyberField } from "../components/cyberui/field";
import { Switch } from "../components/cyberui/switch";
import { Button, Input } from "./controls";
import panelStyles from "../components/cyberui/panel.module.css";

export { Button, Input, Select, Slider, Textarea, Progress, HoldButton } from "./controls";

export type Tone = "good" | "warn" | "bad" | "neutral";
export function Badge({
  children,
  tone = "neutral",
}: {
  children: ReactNode;
  tone?: Tone;
}) {
  return (
    <CyberBadge tone={{ good: "success", warn: "warning", bad: "danger", neutral: "default" }[tone] as "success" | "warning" | "danger" | "default"} dot>{children}</CyberBadge>
  );
}
export function Panel({
  title,
  description,
  action,
  children,
  className = "",
  shape = "header",
}: {
  title: string;
  description?: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
  shape?: PanelShape;
}) {
  return (
    <CyberPanel shape={shape} className={`panel ${className}`}>
      <div className={shape === "header" ? `${panelStyles.panelTitle} panel-heading` : "panel-heading plain-heading"}>
        <h2>{title}</h2>
        {action}
      </div>
      {description && <p className="panel-description">{description}</p>}
      {children}
    </CyberPanel>
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
    <div className="notice">
      <Alert title={typeof children === "string" ? children : "设备提示"}
        tone={{ good: "success", warn: "warning", bad: "danger", neutral: "info" }[tone] as "success" | "warning" | "danger" | "info"}>
        {typeof children === "string" ? undefined : children}
      </Alert>
      {retry && (
        <Button type="button" size="sm" onPress={retry}>
          <RefreshCw size={14} aria-hidden="true" />
          重试
        </Button>
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
    <EmptyState title={title} description={typeof children === "string" ? children : undefined}
      action={typeof children === "string" ? undefined : children} />
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
    <CyberField label={label} description={help}>{children}</CyberField>
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
    <div className="toggle-row">
      <Switch label={label} isSelected={checked} isDisabled={disabled} onChange={onChange} />
      {help && <p className="muted">{help}</p>}
    </div>
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
          <Input
            ref={ref}
            value={value || "暂不可用"}
            readOnly
            onFocus={(event) => event.currentTarget.select()}
          />
          <Button
            type="button"
            className="icon-action"
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
          </Button>
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
