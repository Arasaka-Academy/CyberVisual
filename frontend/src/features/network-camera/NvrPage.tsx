import { Button, Input, Textarea, Select } from "../../shared/controls";
import { Panel as CyberPanel } from "../../components/cyberui/panel";
import { ConfigSection, ConfigUnavailable } from "../settings/ConfigSection";
import { useRef, useState } from "react";
import { CheckCircle2, Circle, Copy, Radio, Video } from "lucide-react";
import {
  Badge,
  CopyField,
  Field,
  Notice,
  Panel,
  Toggle,
  stateLabel,
  stateTone,
} from "../../shared/components";
import type { ConfigManager } from "../settings/useConfigManager";
import type { NetworkCameraConfig } from "./types";
import type { RuntimeStatus } from "../runtime/types";

export default function Nvr({
  status,
  manager,
  stale,
}: {
  status: RuntimeStatus | null;
  manager: ConfigManager;
  stale: boolean;
}) {
  const network = status?.network_camera;
  const settings = manager.draft?.network_camera;
  const [copyMessage, setCopyMessage] = useState("");
  const [manualCopy, setManualCopy] = useState(false);
  const copyRef = useRef<HTMLTextAreaElement>(null);
  const connectionText = [
    "CyberVisual · NVR 接入",
    `ONVIF: ${network?.onvif_url || "暂不可用"}`,
    `UUID: ${network?.device_uuid || "暂不可用"}`,
    ...(network?.profiles || []).flatMap((profile) => [
      `${profile.token}: ${profile.rtsp_uri || "暂不可用"}`,
      `Snapshot: ${profile.snapshot_uri || "暂不可用"}`,
    ]),
    "视频：H.264；传输：TCP / UDP；认证：设备 Digest 账号",
  ].join("\n");
  const set = (patch: Partial<NetworkCameraConfig>) =>
    manager.edit({ network_camera: patch });
  const checks = [
    {
      title: "设备协议账号",
      detail: network
        ? network.credentials_configured
          ? "已配置"
          : "未配置"
        : "未知",
      good: !!network?.credentials_configured,
    },
    {
      title: "ONVIF / RTSP 服务",
      detail: stale ? "等待更新" : stateLabel(network?.state),
      good: !stale && network?.state === "running",
    },
    {
      title: "WS-Discovery 发现",
      detail: stale ? "等待更新" : stateLabel(network?.discovery?.state),
      good: !stale && network?.discovery?.state === "running",
    },
    {
      title: "事件源",
      detail:
        stale || !network
          ? "未知"
          : network.events?.online
            ? "分析在线"
            : "分析离线",
      good: !stale && !!network?.events?.online,
    },
  ];
  return (
    <div className="page-stack">
      <div className="page-action-row">
        <p className="page-description">
          让外部 NVR 发现、管理并获取这台摄像头的视频。
        </p>
        <Button
          type="button"
          disabled={!network}
          onClick={async () => {
            try {
              if (!navigator.clipboard?.writeText) throw new Error();
              await navigator.clipboard.writeText(connectionText);
              setCopyMessage("接入信息已复制。");
              setManualCopy(false);
            } catch {
              setManualCopy(true);
              setCopyMessage("请选择下方接入信息，手动复制。");
              window.setTimeout(() => {
                copyRef.current?.focus();
                copyRef.current?.select();
              }, 0);
            }
          }}
        >
          <Copy size={16} aria-hidden="true" />
          复制接入信息
        </Button>
      </div>
      {copyMessage && (
        <p className="save-notice" role="status">
          {copyMessage}
        </p>
      )}
      {manualCopy && (
        <Textarea
          ref={copyRef}
          className="connection-export"
          label="接入信息"
          value={connectionText}
          readOnly
          onFocus={(event) => event.currentTarget.select()}
          rows={8}
        />
      )}
      <div className="readiness-grid">
        {checks.map((check) => (
          <CyberPanel shape="rail" className="readiness-card" key={check.title}>
            {check.good ? (
              <CheckCircle2
                size={18}
                className="good-text"
                aria-hidden="true"
              />
            ) : (
              <Circle size={18} className="muted" aria-hidden="true" />
            )}
            <div>
              <span>{check.title}</span>
              <strong>{check.detail}</strong>
            </div>
          </CyberPanel>
        ))}
      </div>
      {!network && (
        <Notice tone="neutral">
          {status
            ? "当前服务未提供网络摄像头状态，请确认后端版本。"
            : "正在读取网络摄像头状态…"}
        </Notice>
      )}
      {network?.last_error && <Notice>{network.last_error}</Notice>}
      {network?.discovery?.last_error && (
        <Notice>发现服务：{network.discovery.last_error}</Notice>
      )}
      {status?.camera.error && (
        <Notice>采集视频源：{status.camera.error}</Notice>
      )}
      {network?.events?.last_error && (
        <Notice>AI 分析源：{network.events.last_error}</Notice>
      )}
      {network && !network.credentials_configured && (
        <Notice tone="warn">
          尚未配置设备协议账号。请在服务部署环境中设置{" "}
          <code>CYBERVISUAL_ONVIF_USERNAME</code> 与{" "}
          <code>CYBERVISUAL_ONVIF_PASSWORD</code>
          ，重启服务后再启用协议。账号与密码不会在此页面读取或保存。
        </Notice>
      )}
      <Panel
        title="设备管理入口"
        description="在 NVR 中选择 ONVIF，使用已部署的设备账号认证"
        action={
          <Badge tone={stale ? "neutral" : stateTone(network?.state)}>
            {stale ? "等待更新" : stateLabel(network?.state)}
          </Badge>
        }
      >
        <div className="form-grid">
          <CopyField label="ONVIF 服务地址" value={network?.onvif_url} />
          <CopyField label="设备 UUID" value={network?.device_uuid} />
        </div>
        <p className="muted panel-note">
          发现端口 UDP 3702；HTTP
          服务端口使用当前部署配置。无法自动发现时，可手动填写 ONVIF 地址。
        </p>
      </Panel>
      <div className="profile-grid">
        {["raw", "annotated"].map((token) => {
          const profile = network?.profiles?.find(
            (item) => item.token === token,
          );
          const applied = manager.applied?.network_camera;
          const active = !stale && !!profile?.active;
          return (
            <Panel
              key={token}
              className="profile-card"
              shape="brackets"
              title={token === "raw" ? "原始视频" : "AI 标注视频"}
              description={
                token === "raw"
                  ? "原始画面，不依赖推理速度"
                  : "带检测框画面，随推理结果更新"
              }
              action={
                <span className="profile-icon">
                  <Video size={19} aria-hidden="true" />
                </span>
              }
            >
              <div className="profile-meta">
                <code>Profile · {token}</code>
                <Badge
                  tone={
                    profile?.last_error ? "bad" : active ? "good" : "neutral"
                  }
                >
                  {profile?.last_error
                    ? "输出故障"
                    : active
                      ? "正在发布"
                      : !stale && network?.state === "running"
                        ? "等待取流"
                        : "尚未发布"}
                </Badge>
              </div>
              <CopyField
                label={`${token === "raw" ? "原始" : "标注"} RTSP 地址`}
                value={profile?.rtsp_uri}
              />
              <CopyField
                label={`${token === "raw" ? "原始" : "标注"}快照地址`}
                value={profile?.snapshot_uri}
              />
              <dl className="detail-list">
                <div>
                  <dt>视频格式</dt>
                  <dd>H.264</dd>
                </div>
                <div>
                  <dt>配置帧率上限</dt>
                  <dd>
                    {applied
                      ? `${token === "raw" ? applied.raw_fps : applied.annotated_fps} FPS`
                      : "—"}
                  </dd>
                </div>
                <div>
                  <dt>配置码率</dt>
                  <dd>
                    {applied
                      ? `${token === "raw" ? applied.raw_bitrate_kbps : applied.annotated_bitrate_kbps} kbps`
                      : "—"}
                  </dd>
                </div>
                <div>
                  <dt>已发布帧数</dt>
                  <dd>{profile?.frames ?? "—"}</dd>
                </div>
              </dl>
              {profile?.last_error && <Notice>{profile.last_error}</Notice>}
            </Panel>
          );
        })}
      </div>
      <div className="nvr-bottom-grid">
        <div className="page-stack">
          {!settings ? (
            <ConfigUnavailable manager={manager} />
          ) : (
            <ConfigSection
              manager={manager}
              group="network"
              title="协议配置"
              description="修改本设备对外提供的 ONVIF 与 RTSP 服务"
              warning="保存协议配置会重启输出，中断现有 RTSP 视频与 ONVIF 订阅。外部客户端需要重新连接。"
            >
              <Toggle
                label="启用网络摄像头协议"
                help="向 NVR 提供视频、发现与事件接口"
                checked={settings.enabled}
                disabled={!network?.credentials_configured && !settings.enabled}
                onChange={(enabled) => set({ enabled })}
              />
              <div className="form-grid">
                <Field label="公布的 IPv4 地址" help="留空时自动选择局域网地址">
                  <Input
                    placeholder="自动选择"
                    value={settings.advertise_host}
                    onChange={(event) =>
                      set({ advertise_host: event.target.value })
                    }
                  />
                </Field>
                <Field label="RTSP 端口">
                  <Input
                    type="number"
                    min={1024}
                    max={65535}
                    required
                    value={settings.rtsp_port}
                    onChange={(event) =>
                      set({ rtsp_port: Number(event.target.value) })
                    }
                  />
                </Field>
                <Select label="编码器"
                    value={settings.encoder}
                    onChange={(value) =>
                      set({
                        encoder: value as NetworkCameraConfig["encoder"],
                      })
                    }
                   options={[{"id":"auto","label":"自动选择"},{"id":"jetson","label":"Jetson 硬件编码"},{"id":"software","label":"软件编码"}]} />
                <div className="field read-only-field">
                  <span>实际编码器</span>
                  <strong>{network?.encoder || "尚未选择"}</strong>
                </div>
              </div>
              <details className="advanced">
                <summary>发现与视频参数</summary>
                <Toggle
                  label="启用 WS-Discovery"
                  checked={settings.discovery_enabled}
                  onChange={(discovery_enabled) => set({ discovery_enabled })}
                />
                <Field label="发现网络接口 IPv4" help="留空时使用默认接口">
                  <Input
                    value={settings.discovery_interface}
                    placeholder="默认接口"
                    onChange={(event) =>
                      set({ discovery_interface: event.target.value })
                    }
                  />
                </Field>
                <div className="form-grid">
                  {(["raw", "annotated"] as const).map((kind) => (
                    <div className="page-stack" key={kind}>
                      <Field
                        label={`${kind === "raw" ? "原始" : "标注"}帧率上限（FPS）`}
                      >
                        <Input
                          type="number"
                          required
                          min={1}
                          max={kind === "raw" ? 30 : 15}
                          value={settings[`${kind}_fps`]}
                          onChange={(event) =>
                            set({ [`${kind}_fps`]: Number(event.target.value) })
                          }
                        />
                      </Field>
                      <Field
                        label={`${kind === "raw" ? "原始" : "标注"}码率（kbps）`}
                      >
                        <Input
                          type="number"
                          required
                          min={64}
                          max={20000}
                          value={settings[`${kind}_bitrate_kbps`]}
                          onChange={(event) =>
                            set({
                              [`${kind}_bitrate_kbps`]: Number(
                                event.target.value,
                              ),
                            })
                          }
                        />
                      </Field>
                    </div>
                  ))}
                </div>
              </details>
            </ConfigSection>
          )}
        </div>
        <Panel
          title="客户端接入步骤"
          description="录像与回放在外部 NVR 或 CyberOS 中进行"
        >
          <ol className="steps">
            <li>
              <strong>确认服务就绪</strong>
              <p>部署账号，启用协议，并确认公布的地址可从 NVR 访问。</p>
            </li>
            <li>
              <strong>添加 ONVIF 设备</strong>
              <p>自动发现或手动填写管理地址，使用同一设备账号认证。</p>
            </li>
            <li>
              <strong>选择视频 Profile</strong>
              <p>
                raw 获取原始画面；annotated 获取 AI
                标注画面。两路共享同一摄像头与云台。
              </p>
            </li>
            <li>
              <strong>选择传输方式</strong>
              <p>
                支持 RTP/UDP 与 RTSP/TCP。跨网段或丢包较多时，优先尝试 TCP。
              </p>
            </li>
          </ol>
          <div className="information-note">
            <Radio size={18} aria-hidden="true" />
            <p>
              服务运行或视频正在发布，仅表示本设备输出状态；外部 NVR
              是否接收和录像，请在对应客户端确认。
            </p>
          </div>
          <p className="muted panel-note">
            ONVIF 支持 UsernameToken Digest；RTSP 与快照使用 Digest 认证。
          </p>
        </Panel>
      </div>
    </div>
  );
}
