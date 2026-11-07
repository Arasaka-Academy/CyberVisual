import { ConfigSection, ConfigUnavailable } from "./ConfigSection";
import { useEffect, useRef, useState } from "react";
import {
  Badge,
  Field,
  LinkAction,
  Notice,
  Toggle,
} from "../../shared/components";
import type { ConfigManager } from "../settings/useConfigManager";
import type { RuntimeConfig } from "./types";
import type { RuntimeStatus } from "../runtime/types";

export default function Settings({
  manager,
  status,
}: {
  manager: ConfigManager;
  status: RuntimeStatus | null;
}) {
  const ptzSection = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const reveal = () => {
      if (window.location.hash.includes("section=ptz")) {
        ptzSection.current?.scrollIntoView?.({ block: "start" });
        ptzSection.current?.focus({ preventScroll: true });
      }
    };
    reveal();
    window.addEventListener("hashchange", reveal);
    return () => window.removeEventListener("hashchange", reveal);
  }, [manager.applied]);
  const config = manager.draft;
  if (!config) return <ConfigUnavailable manager={manager} />;
  const set = manager.edit;
  return (
    <div className="settings-layout">
      <div className="page-stack settings-main">
        <ConfigSection
          manager={manager}
          group="camera"
          title="视频源"
          description="配置本设备唯一的物理摄像头或测试视频源"
          warning="修改采集源或分辨率会重新打开视频源，短暂中断画面与 AI 分析。"
        >
          <div className="form-grid">
            <Field label="输入来源">
              <select
                value={config.source}
                onChange={(event) =>
                  set({ source: event.target.value as RuntimeConfig["source"] })
                }
              >
                <option value="camera">物理摄像头</option>
                <option value="synthetic">合成测试画面</option>
                <option value="video">本地视频文件</option>
              </select>
            </Field>
            <Field label="采集帧率（FPS）">
              <input
                type="number"
                min={1}
                max={240}
                required
                value={config.camera_fps}
                onChange={(event) =>
                  set({ camera_fps: Number(event.target.value) })
                }
              />
            </Field>
            {config.source === "camera" && (
              <>
                <Field label="摄像头序号">
                  <input
                    type="number"
                    min={0}
                    max={32}
                    required
                    value={config.camera_index}
                    onChange={(event) =>
                      set({ camera_index: Number(event.target.value) })
                    }
                  />
                </Field>
                <Field label="设备路径" help="可留空，使用摄像头序号">
                  <input
                    placeholder="例如 /dev/video0"
                    value={config.camera_device}
                    onChange={(event) =>
                      set({ camera_device: event.target.value })
                    }
                  />
                </Field>
              </>
            )}
            {config.source === "video" && (
              <Field label="设备上的视频文件路径">
                <input
                  required
                  value={config.sample_video}
                  onChange={(event) =>
                    set({ sample_video: event.target.value })
                  }
                />
              </Field>
            )}
            <Field label="画面宽度（px）" help="H.264 输出要求宽高为偶数">
              <input
                type="number"
                min={160}
                max={3840}
                step={2}
                required
                value={config.resolution.width}
                onChange={(event) =>
                  set({
                    resolution: {
                      ...config.resolution,
                      width: Number(event.target.value),
                    },
                  })
                }
              />
            </Field>
            <Field label="画面高度（px）">
              <input
                type="number"
                min={120}
                max={2160}
                step={2}
                required
                value={config.resolution.height}
                onChange={(event) =>
                  set({
                    resolution: {
                      ...config.resolution,
                      height: Number(event.target.value),
                    },
                  })
                }
              />
            </Field>
          </div>
          <details className="advanced">
            <summary>采集与预览高级参数</summary>
            <div className="form-grid">
              <Field label="摄像头 FourCC">
                <input
                  maxLength={4}
                  value={config.camera_fourcc}
                  onChange={(event) =>
                    set({ camera_fourcc: event.target.value })
                  }
                />
              </Field>
              <Field label="MJPEG 画质">
                <input
                  type="number"
                  min={35}
                  max={95}
                  required
                  value={config.jpeg_quality}
                  onChange={(event) =>
                    set({ jpeg_quality: Number(event.target.value) })
                  }
                />
              </Field>
              <Field label="采集重试间隔（秒）">
                <input
                  type="number"
                  min={0.1}
                  max={30}
                  step={0.1}
                  required
                  value={config.retry_interval_seconds}
                  onChange={(event) =>
                    set({ retry_interval_seconds: Number(event.target.value) })
                  }
                />
              </Field>
            </div>
          </details>
        </ConfigSection>
        <ConfigSection
          manager={manager}
          group="ai"
          title="AI 检测"
          description="检测阈值与类别过滤同时应用于标注视频和 AI 事件"
        >
          <div className="form-grid">
            <Field label="检测后端">
              <select
                value={config.detector_backend}
                onChange={(event) =>
                  set({
                    detector_backend: event.target
                      .value as RuntimeConfig["detector_backend"],
                  })
                }
              >
                <option value="auto">自动选择</option>
                <option value="tensorrt">TensorRT</option>
                <option value="opencv">OpenCV</option>
                <option value="mock">模拟检测</option>
              </select>
            </Field>
            <Field label="模型文件路径">
              <input
                required
                value={config.model_path}
                onChange={(event) => set({ model_path: event.target.value })}
              />
            </Field>
            <Field label="置信度阈值">
              <input
                type="number"
                min={0}
                max={1}
                step={0.01}
                required
                value={config.confidence}
                onChange={(event) =>
                  set({ confidence: Number(event.target.value) })
                }
              />
            </Field>
            <Field label="IoU 阈值">
              <input
                type="number"
                min={0}
                max={1}
                step={0.01}
                required
                value={config.iou}
                onChange={(event) => set({ iou: Number(event.target.value) })}
              />
            </Field>
          </div>
          <ClassFilter
            value={config.class_allowlist}
            onChange={(class_allowlist) => set({ class_allowlist })}
          />
        </ConfigSection>
        <ConfigSection
          manager={manager}
          group="snapshot"
          title="自动快照"
          description="检测到指定类别时，将图片与元数据保存到设备"
        >
          <Toggle
            label="启用自动快照"
            checked={config.auto_snapshot_enabled}
            onChange={(auto_snapshot_enabled) => set({ auto_snapshot_enabled })}
          />
          <div className="form-grid">
            <Field label="触发类别">
              <input
                required
                value={config.auto_snapshot_label}
                onChange={(event) =>
                  set({ auto_snapshot_label: event.target.value })
                }
              />
            </Field>
            <Field label="冷却时间（秒）">
              <input
                type="number"
                min={1}
                max={3600}
                step={1}
                required
                value={config.auto_snapshot_cooldown_seconds}
                onChange={(event) =>
                  set({
                    auto_snapshot_cooldown_seconds: Number(event.target.value),
                  })
                }
              />
            </Field>
          </div>
          {status?.auto_snapshot.last_error && (
            <Notice>{status.auto_snapshot.last_error}</Notice>
          )}
        </ConfigSection>
        <div ref={ptzSection} tabIndex={-1} className="settings-anchor">
          <ConfigSection
            manager={manager}
            group="ptz"
            title="云台驱动"
            description="选择与 ONVIF 和浏览器共用的云台驱动"
            warning="切换驱动会重启协议输出，停止当前云台动作。"
          >
            <Field label="驱动类型">
              <select
                value={config.network_camera!.ptz_driver}
                onChange={(event) =>
                  set({
                    network_camera: {
                      ptz_driver: event.target.value as
                        "disabled" | "simulated",
                    },
                  })
                }
              >
                <option value="disabled">禁用云台（生产默认）</option>
                <option value="simulated">模拟驱动（仅验证位置变化）</option>
              </select>
            </Field>
            <p className="muted">
              当前模拟驱动不控制真实电机，也不会改变视频画面。真实驱动需在硬件确定后接入。
            </p>
            {!manager.applied?.network_camera?.enabled && (
              <Notice tone="neutral">
                云台还需要启用网络摄像头协议。
                <LinkAction to="#/nvr">前往 NVR 接入配置</LinkAction>
              </Notice>
            )}
          </ConfigSection>
        </div>
      </div>
      <aside className="settings-aside">
        <section className="panel">
          <span className="eyebrow">配置工作流</span>
          <h2>按功能独立保存</h2>
          <p>
            修改先保存在页面草稿中，只有点击对应区域的保存按钮才会应用到设备。
          </p>
          <div className="settings-tip">
            <Badge tone={manager.dirty ? "warn" : "neutral"}>
              {manager.dirty ? "有未保存的修改" : "配置已同步"}
            </Badge>
            <p>切换工作区会保留草稿；刷新或关闭页面前请保存。</p>
          </div>
          <LinkAction to="#/nvr">管理 ONVIF / RTSP 配置</LinkAction>
        </section>
      </aside>
    </div>
  );
}
function ClassFilter({
  value,
  onChange,
}: {
  value: string[];
  onChange: (value: string[]) => void;
}) {
  // Preserve delimiters while typing; normalize only when leaving the field.
  const [text, setText] = useState(value.join(", "));
  useEffect(() => setText(value.join(", ")), [value]);
  return (
    <Field
      label="允许检测的类别"
      help="逗号分隔英文类别；留空表示全部，例如 person, car"
    >
      <input
        value={text}
        onChange={(event) => setText(event.target.value)}
        onBlur={() =>
          onChange(
            text
              .split(/[,，]/)
              .map((item) => item.trim())
              .filter(Boolean),
          )
        }
      />
    </Field>
  );
}
