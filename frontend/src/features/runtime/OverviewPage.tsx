import {
  Activity,
  ArrowUpRight,
  Camera,
  Cpu,
  Move,
  Network,
  Radio,
  Thermometer,
} from "lucide-react";
import {
  Badge,
  Empty,
  LinkAction,
  Notice,
  Panel,
  stateLabel,
  stateTone,
} from "../../shared/components";
import type { RuntimeConfig } from "../settings/types";
import type { RuntimeStatus } from "./types";

export default function Overview({
  status,
  config,
  stale,
}: {
  status: RuntimeStatus | null;
  config: RuntimeConfig | null;
  stale: boolean;
}) {
  if (!status)
    return (
      <Empty title="正在连接 CyberVisual…">设备状态就绪后会显示在这里。</Empty>
    );
  const network = status.network_camera;
  const cameraFresh =
    !stale &&
    !!status.last_frame_ts &&
    Date.now() - status.last_frame_ts * 1000 <= 5000;
  const services = [
    {
      icon: Camera,
      title: "视频采集",
      value: status.camera.connected && cameraFresh ? "采集中" : "等待视频源",
      description: status.camera.error || `来源：${status.camera.source}`,
      good: status.camera.connected && cameraFresh,
      to: "#/monitor",
    },
    {
      icon: Cpu,
      title: "AI 推理",
      value: status.model.loaded ? "模型已加载" : "模型未就绪",
      description:
        status.model.error ||
        `${status.model.backend} · ${status.detection_count} 个当前目标`,
      good: status.model.loaded,
      to: "#/settings",
    },
    {
      icon: Network,
      title: "ONVIF / RTSP",
      value: stateLabel(network?.state),
      description: network?.last_error || "向 NVR 提供管理、视频与快照",
      good: network?.state === "running",
      to: "#/nvr",
    },
    {
      icon: Move,
      title: "云台驱动",
      value: network?.ptz?.simulated
        ? "模拟驱动"
        : stateLabel(network?.ptz?.state),
      description:
        network?.ptz?.last_error ||
        (network?.ptz?.simulated ? "仅验证位置变化" : "与 ONVIF 共享云台控制"),
      good: network?.ptz?.enabled && network?.ptz?.state !== "unavailable",
      to: "#/monitor",
    },
  ];
  return (
    <div className="page-stack">
      <section className="overview-intro">
        <div>
          <span className="eyebrow">设备工作区</span>
          <h2>本地摄像头，运行状态一览。</h2>
          <p>集中查看采集、分析与云台状态，管理设备对外的视频和事件接口。</p>
        </div>
        <a className="button primary" href="#/monitor">
          <Camera size={17} aria-hidden="true" />
          进入实时监看
          <ArrowUpRight size={16} aria-hidden="true" />
        </a>
      </section>
      {status.last_error && <Notice>{status.last_error}</Notice>}
      <div className="service-grid">
        {services.map(({ icon: Icon, title, value, description, good, to }) => (
          <a href={to} className="service-card" key={title}>
            <div className="service-top">
              <span className="service-icon">
                <Icon size={20} aria-hidden="true" />
              </span>
              <ArrowUpRight size={17} aria-hidden="true" />
            </div>
            <span className="muted">{title}</span>
            <h3>{stale ? "等待状态更新" : value}</h3>
            <p>{description}</p>
            <span
              className={`service-indicator ${good && !stale ? "on" : ""}`}
              aria-hidden="true"
            />
          </a>
        ))}
      </div>
      <div className="overview-detail-grid">
        <Panel title="运行指标" description="来自设备当前运行状态">
          <div className="metric-grid">
            <Metric
              icon={<Activity size={17} />}
              label="推理帧率"
              value={`${status.fps.toFixed(1)}`}
              unit="FPS"
            />
            <Metric
              icon={<Radio size={17} />}
              label="推理延迟"
              value={
                status.latency_ms == null ? "—" : status.latency_ms.toFixed(0)
              }
              unit="ms"
            />
            <Metric
              icon={<Thermometer size={17} />}
              label="设备温度"
              value={
                status.temperature_c == null
                  ? "—"
                  : status.temperature_c.toFixed(1)
              }
              unit="°C"
            />
            <Metric
              icon={<Cpu size={17} />}
              label="内存使用"
              value={status.memory ? status.memory.percent.toFixed(1) : "—"}
              unit="%"
            />
          </div>
          {stale && (
            <p className="muted panel-note">以上为上次成功读取的数据。</p>
          )}
        </Panel>
        <Panel
          title="接入准备"
          description="将本设备加入 NVR 或 CyberOS"
          action={<LinkAction to="#/nvr">查看接入</LinkAction>}
        >
          <div className="check-list">
            <CheckRow
              label="设备协议账号"
              value={
                network
                  ? network.credentials_configured
                    ? "已配置"
                    : "待配置"
                  : "未知"
              }
              good={!!network?.credentials_configured}
            />
            <CheckRow
              label="ONVIF 发现"
              value={stateLabel(network?.discovery?.state)}
              good={network?.discovery?.state === "running"}
            />
            <CheckRow
              label="视频 Profile"
              value={network ? `${network.profiles.length} 路 · H.264` : "未知"}
              good={!!network?.enabled}
            />
          </div>
          <p className="muted panel-note">
            账号通过部署环境配置。录像与回放由外部 NVR 管理。
          </p>
        </Panel>
      </div>
      <Panel
        title="AI 状态"
        description="基于连续推理的人物与车辆存在状态"
        action={<LinkAction to="#/events">查看事件</LinkAction>}
      >
        <div className="presence-summary">
          {["person", "vehicle"].map((category) => (
            <div key={category}>
              <span className="muted">
                {category === "person" ? "人物" : "车辆"}
              </span>
              <Badge
                tone={
                  !stale &&
                  network?.events?.online &&
                  network.events.presence[category]
                    ? "good"
                    : "neutral"
                }
              >
                {stale || !network?.events?.online
                  ? "状态未知"
                  : network.events.presence[category]
                    ? "当前存在"
                    : "当前未检出"}
              </Badge>
            </div>
          ))}
          <div>
            <span className="muted">视频分辨率</span>
            <strong>
              {config
                ? `${config.resolution.width} × ${config.resolution.height}`
                : "—"}
            </strong>
          </div>
          <div>
            <span className="muted">自动快照</span>
            <strong>
              {status.auto_snapshot.enabled
                ? `已保存 ${status.auto_snapshot.count} 张`
                : "已关闭"}
            </strong>
          </div>
        </div>
      </Panel>
    </div>
  );
}
function Metric({
  icon,
  label,
  value,
  unit,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  unit: string;
}) {
  return (
    <div className="metric">
      <span>
        {icon}
        {label}
      </span>
      <strong>
        {value}
        <small>{unit}</small>
      </strong>
    </div>
  );
}
function CheckRow({
  label,
  value,
  good,
}: {
  label: string;
  value: string;
  good: boolean;
}) {
  return (
    <div>
      <span>{label}</span>
      <Badge tone={good ? "good" : "neutral"}>{value}</Badge>
    </div>
  );
}
