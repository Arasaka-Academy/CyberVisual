import { Button, Input, HoldButton, Slider, Progress } from "../../shared/controls";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  ArrowDown,
  ArrowLeft,
  ArrowRight,
  ArrowUp,
  Crosshair,
  Home,
  Plus,
  Square,
  Trash2,
} from "lucide-react";
import { calibratePTZ, commandPTZ, getPTZ } from "./api";
import {
  Badge,
  Empty,
  Field,
  Freshness,
  LinkAction,
  Notice,
  Panel,
  stateLabel,
  stateTone,
} from "../../shared/components";
import { errorMessage, usePoll } from "../../shared/hooks";
import type { PTZCommand } from "./types";

export default function PTZPanel({
  visible,
  now,
}: {
  visible: boolean;
  now: number;
}) {
  const ptz = usePoll(getPTZ, 500, visible);
  const [speed, setSpeed] = useState(0.3);
  const [holding, setHolding] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [name, setName] = useState("");
  const [deleting, setDeleting] = useState("");
  const [confirmCenter, setConfirmCenter] = useState(false);
  const [pan, setPan] = useState(0);
  const [tilt, setTilt] = useState(0);
  const [step, setStep] = useState(0.1);
  const mounted = useRef(true);
  const active = useRef(false);
  const mayMove = useRef(false);
  const generation = useRef(0);
  const renewal = useRef<number | undefined>(undefined);
  const queue = useRef<Promise<unknown>>(Promise.resolve());
  const busyRef = useRef(false);
  const status = ptz.data;
  const stale = !ptz.updatedAt || now - ptz.updatedAt > 5000 || !!ptz.error;
  const ready =
    !!status?.enabled && status.state === "running" && !status.calibration_required && !stale && visible;

  const enqueue = useCallback(
    (command: PTZCommand, lease?: number) => {
      const task = queue.current
        .catch(() => undefined)
        .then(async () => {
          if (
            command.action === "continuous_move" &&
            (!active.current || lease !== generation.current)
          )
            return;
          if (!mounted.current && command.action !== "stop") return;
          const next = await commandPTZ(command);
          if (mounted.current) {
            ptz.replace(next);
            ptz.refresh();
          }
        });
      queue.current = task;
      return task;
    },
    [ptz.replace, ptz.refresh],
  );
  const release = useCallback(
    (force = false) => {
      active.current = false;
      generation.current += 1;
      window.clearTimeout(renewal.current);
      if (mounted.current) setHolding(false);
      if (!mayMove.current && !force) return;
      mayMove.current = false;
      void enqueue({ action: "stop" }).catch(() => {
        if (mounted.current)
          setError(
            "停止请求未确认。最后一条连续移动指令将在 2 秒后自动停止；请检查连接。",
          );
      });
    },
    [enqueue],
  );
  useEffect(() => {
    mounted.current = true;
    const stop = () => release();
    const hidden = () => {
      if (document.hidden) release();
    };
    window.addEventListener("blur", stop);
    document.addEventListener("visibilitychange", hidden);
    return () => {
      mounted.current = false;
      release();
      window.removeEventListener("blur", stop);
      document.removeEventListener("visibilitychange", hidden);
    };
  }, [release]);
  useEffect(() => {
    if (!ready) release();
  }, [ready, release]);

  const start = (x: number, y: number) => {
    if (!ready || busyRef.current || active.current) return;
    setError("");
    setNotice("");
    active.current = true;
    mayMove.current = true;
    const lease = ++generation.current;
    setHolding(true);
    const pulse = async () => {
      try {
        await enqueue(
          { action: "continuous_move", pan: x * speed, tilt: y * speed },
          lease,
        );
        if (active.current && lease === generation.current)
          renewal.current = window.setTimeout(pulse, 500);
      } catch (failure) {
        if (mounted.current) setError(errorMessage(failure));
        release();
      }
    };
    void pulse();
  };
  const perform = async (command: PTZCommand, message = "云台指令已执行。") => {
    if (!ready || busyRef.current || active.current) return;
    busyRef.current = true;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await enqueue(command);
      if (mounted.current) {
        setNotice(message);
        if (command.action === "set_preset" && !command.token) setName("");
        setDeleting("");
      }
    } catch (failure) {
      if (mounted.current) setError(errorMessage(failure));
    } finally {
      busyRef.current = false;
      if (mounted.current) setBusy(false);
    }
  };
  const direction = (
    label: string,
    x: number,
    y: number,
    Icon: typeof ArrowUp,
  ) => (
    <HoldButton
      type="button"
      className="direction-button"
      aria-label={label}
      disabled={!ready || busy || !status?.capabilities.continuous_move}
      onPointerDown={(event) => {
        if (event.button !== 0) return;
        event.preventDefault();
        event.currentTarget.setPointerCapture?.(event.pointerId);
        start(x, y);
      }}
      onPointerUp={() => release()}
      onPointerCancel={() => release()}
      onLostPointerCapture={() => release()}
      onBlur={() => release()}
      onKeyDown={(event) => {
        if (event.key === " " || event.key === "Enter") {
          event.preventDefault();
          if (!event.repeat) start(x, y);
        }
      }}
      onKeyUp={(event) => {
        if (event.key === " " || event.key === "Enter") {
          event.preventDefault();
          release();
        }
      }}
    >
      <Icon size={21} aria-hidden="true" />
    </HoldButton>
  );

  return (
    <Panel
      title="云台控制"
      description="与 ONVIF 共用一个云台"
      action={
        <Badge tone={stateTone(status?.state)}>
          {status?.simulated ? "模拟驱动" : stateLabel(status?.state)}
        </Badge>
      }
      className="ptz-panel"
    >
      <Freshness updatedAt={ptz.updatedAt} now={now} error={!!ptz.error} />
      {ptz.error && <Notice retry={ptz.refresh}>{ptz.error}</Notice>}
      {!status ? (
        <Empty title="正在读取云台状态…" />
      ) : (
        <>
          {status.simulated && (
            <div className="simulation-note">
              <Crosshair size={16} aria-hidden="true" />
              <span>模拟模式 · 仅验证位置变化，不驱动真实电机或画面。</span>
            </div>
          )}
          {status.state !== "running" && (
            <Notice tone={status.state === "unavailable" ? "bad" : "neutral"}>
              {status.last_error ||
                "云台尚未启用。在系统设置中选择驱动，并启用网络摄像头协议。"}
              <LinkAction to="#/settings?section=ptz">云台设置</LinkAction>
            </Notice>
          )}
          {error && <Notice>{error}</Notice>}
          {status.calibration_required && (
            <Notice tone="neutral">
              重启或参考失效后需重新标定中心。确认前请将两轴手动置于安全中心；重新标定会清除原预置位。
              <div className="button-row wrap">
                {confirmCenter ? <>
                  <Button disabled={!status.enabled || busy || stale} onClick={() => {
                    setBusy(true); release(true);
                    void queue.current.catch(() => undefined).then(calibratePTZ).then((next) => {
                      if (mounted.current) { ptz.replace(next); setConfirmCenter(false); setNotice("已确认中心并启用云台。"); }
                    }).catch((failure: unknown) => { if (mounted.current) setError(errorMessage(failure)); }).finally(() => { if (mounted.current) setBusy(false); });
                  }}>确认当前位置为中心并启用</Button>
                  <Button onClick={() => setConfirmCenter(false)}>取消</Button>
                </> : <Button disabled={!status.enabled || busy || stale} onClick={() => setConfirmCenter(true)}>{status.hardware_ready ? "标定中心" : "重连并标定中心"}</Button>}
              </div>
            </Notice>
          )}
          {notice && (
            <p className="save-notice" role="status">
              {notice}
            </p>
          )}
          <div className="ptz-drive">
            <div className="direction-pad">
              <span />
              {direction("向上移动", 0, 1, ArrowUp)}
              <span />
              {direction("向左移动", -1, 0, ArrowLeft)}
              <HoldButton
                className="direction-button stop"
                type="button"
                aria-label="停止云台"
                disabled={!status.enabled}
                onClick={() => release(true)}
              >
                <Square size={18} aria-hidden="true" />
              </HoldButton>
              {direction("向右移动", 1, 0, ArrowRight)}
              <span />
              {direction("向下移动", 0, -1, ArrowDown)}
              <span />
            </div>
            <div className="drive-options">
                <Slider label={`移动速度 ${Math.round(speed * 100)}%`}
                  minValue={0.05}
                  maxValue={1}
                  step={0.05}
                  value={speed}
                  isDisabled={!ready || holding || busy}
                  onChange={setSpeed}
                />
              <Button
                type="button"
                disabled={
                  !ready ||
                  holding ||
                  busy ||
                  !status.capabilities.absolute_move
                }
                onClick={() => void perform({ action: "home" })}
              >
                <Home size={16} aria-hidden="true" />
                归位
              </Button>
              <span className="muted">
                {holding ? "移动中 · 松开即停止" : "按住方向移动，松开停止"}
              </span>
            </div>
          </div>
          <div className="position-grid">
            {(["pan", "tilt"] as const).map((axis) => (
              <div key={axis}>
                <span>{axis === "pan" ? "水平 Pan" : "垂直 Tilt"}</span>
                <strong>
                  {status.position ? status.position[axis].toFixed(3) : "—"}
                </strong>
                <Progress
                  label={axis === "pan" ? "水平位置" : "垂直位置"}
                  value={status.position ? (status.position[axis] + 1) * 50 : 50}
                />
              </div>
            ))}
          </div>
          <p className="muted panel-note">
            标准化范围 −1 至 1；键盘可按住空格或 Enter 操作方向键。
          </p>
          <div className="subsection-heading">
            <h3>预置位</h3>
            <span className="muted">{status.presets.length} / 32</span>
          </div>
          <form
            className="preset-create"
            onSubmit={(event) => {
              event.preventDefault();
              void perform(
                { action: "set_preset", name },
                "已保存当前位置为预置位。",
              );
            }}
          >
            <Input
              aria-label="新预置位名称"
              placeholder="为当前位置命名"
              maxLength={64}
              required
              value={name}
              disabled={!ready || busy || holding}
              onChange={(event) => setName(event.target.value)}
            />
            <Button
              type="submit"
              disabled={
                !ready ||
                busy ||
                holding ||
                !name.trim() ||
                status.presets.length >= 32
              }
            >
              <Plus size={16} aria-hidden="true" />
              添加
            </Button>
          </form>
          <div className="preset-list">
            {status.presets.length === 0 ? (
              <p className="muted">尚无预置位。将云台移到目标位置后添加。</p>
            ) : (
              status.presets.map((preset) => (
                <div className="preset-row" key={preset.token}>
                  <div>
                    <strong>{preset.name}</strong>
                    <small>
                      {preset.pan.toFixed(2)} / {preset.tilt.toFixed(2)}
                    </small>
                  </div>
                  <div className="button-row">
                    {deleting === preset.token ? (
                      <>
                        <Button
                          size="sm" variant="danger"
                          disabled={!ready || busy || holding}
                          onClick={() =>
                            void perform(
                              { action: "remove_preset", token: preset.token },
                              "预置位已删除。",
                            )
                          }
                        >
                          确认删除
                        </Button>
                        <Button
                          size="sm"
                          onClick={() => setDeleting("")}
                        >
                          取消
                        </Button>
                      </>
                    ) : (
                      <>
                        <Button
                          size="sm"
                          disabled={!ready || busy || holding}
                          onClick={() =>
                            void perform({
                              action: "goto_preset",
                              token: preset.token,
                            })
                          }
                        >
                          调用
                        </Button>
                        <Button
                          size="sm"
                          disabled={!ready || busy || holding}
                          onClick={() =>
                            void perform(
                              {
                                action: "set_preset",
                                token: preset.token,
                                name: preset.name,
                              },
                              "预置位已更新为当前位置。",
                            )
                          }
                        >
                          覆盖
                        </Button>
                        <Button
                          className="icon-action"
                          size="sm"
                          disabled={!ready || busy || holding}
                          aria-label={`删除预置位${preset.name}`}
                          onClick={() => setDeleting(preset.token)}
                        >
                          <Trash2 size={15} aria-hidden="true" />
                        </Button>
                      </>
                    )}
                  </div>
                </div>
              ))
            )}
          </div>
          <details className="advanced">
            <summary>高级定位与步进</summary>
            <div className="form-grid">
              <Field label="水平目标位置">
                <Input
                  type="number"
                  min={-1}
                  max={1}
                  step={0.05}
                  value={pan}
                  onChange={(event) => setPan(Number(event.target.value))}
                />
              </Field>
              <Field label="垂直目标位置">
                <Input
                  type="number"
                  min={-1}
                  max={1}
                  step={0.05}
                  value={tilt}
                  onChange={(event) => setTilt(Number(event.target.value))}
                />
              </Field>
            </div>
            <Button
              type="button"
              disabled={
                !ready ||
                busy ||
                holding ||
                !status.capabilities.absolute_move ||
                Math.abs(pan) > 1 ||
                Math.abs(tilt) > 1
              }
              onClick={() =>
                void perform({ action: "absolute_move", pan, tilt })
              }
            >
              移动到目标位置
            </Button>
            <Field label="相对步长">
              <Input
                type="number"
                min={0.01}
                max={1}
                step={0.05}
                value={step}
                onChange={(event) => setStep(Number(event.target.value))}
              />
            </Field>
            <div className="button-row wrap">
              {[
                ["左移一步", -1, 0],
                ["右移一步", 1, 0],
                ["上移一步", 0, 1],
                ["下移一步", 0, -1],
              ].map(([label, x, y]) => (
                <Button
                  key={label}
                  size="sm"
                  disabled={
                    !ready ||
                    busy ||
                    holding ||
                    !status.capabilities.relative_move ||
                    step <= 0 ||
                    step > 1
                  }
                  onClick={() =>
                    void perform({
                      action: "relative_move",
                      pan: Number(x) * step,
                      tilt: Number(y) * step,
                    })
                  }
                >
                  {label}
                </Button>
              ))}
            </div>
          </details>
        </>
      )}
    </Panel>
  );
}
