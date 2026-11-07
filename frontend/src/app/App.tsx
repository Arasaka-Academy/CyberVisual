import { usePoll } from "../shared/hooks";
import { useConfigManager } from "../features/settings/useConfigManager";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  Activity,
  ArrowUpRight,
  Camera,
  LayoutDashboard,
  Menu,
  Move,
  Network,
  Settings2,
  Palette,
  ShieldCheck,
} from "lucide-react";
import { getStatus } from "../features/runtime/api";
import { Badge, Freshness, Notice } from "../shared/components";
import { normalizeStatus } from "../features/runtime/model";
import { useNow, useRoute, useVisible } from "./hooks";
import type { Route } from "./hooks";
import Overview from "../features/runtime/OverviewPage";
import Monitor from "../features/stream/MonitorPage";
import Nvr from "../features/network-camera/NvrPage";
import Events from "../features/events/EventsPage";
import Settings from "../features/settings/SettingsPage";
import { AppearanceProvider, AppearanceDialog } from "./appearance";
import { Button } from "../components/cyberui/button";
import { Drawer } from "../components/cyberui/drawer";

const navigation: Array<{
  route: Route;
  label: string;
  short: string;
  icon: typeof Camera;
  description: string;
}> = [
  {
    route: "overview",
    label: "设备总览",
    short: "总览",
    icon: LayoutDashboard,
    description: "本地摄像头，运行状态一览。采集、分析与协议输出独立呈现。",
  },
  {
    route: "monitor",
    label: "实时监看",
    short: "监看",
    icon: Camera,
    description: "视频画面与云台控制",
  },
  {
    route: "nvr",
    label: "NVR 接入",
    short: "NVR",
    icon: Network,
    description: "协议配置与连接诊断",
  },
  {
    route: "events",
    label: "AI 事件",
    short: "事件",
    icon: Activity,
    description: "存在状态与近期事件",
  },
  {
    route: "settings",
    label: "系统设置",
    short: "设置",
    icon: Settings2,
    description: "采集、检测与驱动配置",
  },
];
export default function App() {
  return <AppearanceProvider><Workspace /></AppearanceProvider>;
}
function Workspace() {
  const [appearanceOpen, setAppearanceOpen] = useState(false);
  const [navigationOpen, setNavigationOpen] = useState(false);
  const route = useRoute();
  const visible = useVisible();
  const now = useNow(visible);
  const runtime = usePoll(getStatus, 1000, visible);
  const manager = useConfigManager(visible);
  const status = useMemo(
    () => (runtime.data ? normalizeStatus(runtime.data) : null),
    [runtime.data],
  );
  const main = useRef<HTMLElement>(null);
  const stale =
    !runtime.updatedAt || now - runtime.updatedAt > 5000 || !!runtime.error;
  const current = navigation.find((item) => item.route === route)!;
  useEffect(() => {
    document.title = `${current.label} · CyberVisual`;
    if (!window.location.hash.includes("section=ptz")) {
      main.current?.focus({ preventScroll: true });
      window.scrollTo?.({ top: 0 });
    }
  }, [route, current.label]);
  const healthy = !!status && status.health === "running" && !stale;
  const navigationLinks = (
    <nav className="main-navigation" aria-label="主导航">
      {navigation.map(({ route: target, label, icon: Icon }, index) => (
        <a key={target} href={`#/${target}`} className={`nav-item ${route === target ? "active" : ""}`}
          aria-current={route === target ? "page" : undefined} onClick={() => setNavigationOpen(false)}>
          <Icon size={18} aria-hidden="true" /><span>{label}</span>
          <span className="nav-index" aria-hidden="true">0{index + 1}</span>
        </a>
      ))}
    </nav>
  );
  return (
    <div className="app-shell">
      <a
        className="skip-link"
        href="#main-content"
        onClick={(event) => {
          event.preventDefault();
          main.current?.focus();
        }}
      >
        跳到主要内容
      </a>
      <aside className="sidebar">
        <a
          className="brand"
          href="#/overview"
          aria-label="CyberVisual 设备总览"
        >
          <span className="brand-mark">
            <Camera size={22} aria-hidden="true" />
          </span>
          <span>
            <strong>CyberVisual</strong>
            <small>EDGE VISION / WORKSPACE</small>
          </span>
        </a>
        <span className="nav-section-label">设备工作区</span>
        {navigationLinks}
        <div className="sidebar-footer">
          <div>
            <span className={`connection-dot ${healthy ? "on" : ""}`} />
            <span>
              {healthy
                ? "设备连接正常"
                : stale && status
                  ? "等待设备更新"
                  : "正在读取状态"}
            </span>
          </div>
          <p>本地设备 · 单路视频源</p>
          <a href="#/nvr">
            ONVIF + RTSP
            <ArrowUpRight size={13} aria-hidden="true" />
          </a>
        </div>
      </aside>
      <div className="workspace">
        <header className="topbar">
          <Button className="menu-trigger icon-action" aria-label="打开导航" onPress={() => setNavigationOpen(true)}><Menu size={19} aria-hidden="true" /></Button>
          <span className="header-context">CYBERVISUAL <span>/</span> DEVICE CONSOLE</span>
          <div className="topbar-status">
            <Badge
              tone={
                stale
                  ? "neutral"
                  : status?.health === "thermal_warning"
                    ? "warn"
                    : healthy
                      ? "good"
                      : status?.health === "error"
                        ? "bad"
                        : "neutral"
              }
            >
              {!status
                ? "连接中"
                : stale
                  ? "状态待更新"
                  : status.health === "thermal_warning"
                    ? "温度偏高"
                    : healthy
                      ? "设备运行中"
                      : "设备待就绪"}
            </Badge>
            <Freshness
              updatedAt={runtime.updatedAt}
              now={now}
              error={!!runtime.error}
            />
          </div>
          <Button className="icon-action appearance-trigger" aria-label="外观设置" onPress={() => setAppearanceOpen(true)}>
            <Palette size={19} aria-hidden="true" />
          </Button>
        </header>
        <main
          id="main-content"
          ref={main}
          tabIndex={-1}
          aria-label={current.label}
          className="main-content"
        >
          <div className="page-heading">
            <div>
            <span className="eyebrow">DEVICE WORKSPACE / 0{navigation.indexOf(current) + 1}</span>
            <h1>{current.label}<span className="terminal-cursor" aria-hidden="true">_</span></h1>
            <p>{current.description}</p>
            </div>
            {route === "overview" && <Button variant="primary" onPress={() => { window.location.hash = "/monitor"; }}>
              <Camera size={17} aria-hidden="true" />进入实时监看<ArrowUpRight size={16} aria-hidden="true" />
            </Button>}
          </div>
          {runtime.error && (
            <Notice retry={runtime.refresh}>
              状态更新失败：{runtime.error}
            </Notice>
          )}
          {manager.error && manager.applied && (
            <Notice retry={manager.retry}>配置刷新失败：{manager.error}</Notice>
          )}
          {route === "overview" && (
            <Overview status={status} config={manager.applied} stale={stale} />
          )}
          {route === "monitor" && (
            <Monitor
              status={status}
              visible={visible}
              now={now}
              stale={stale}
            />
          )}
          {route === "nvr" && (
            <Nvr status={status} manager={manager} stale={stale} />
          )}
          {route === "events" && <Events visible={visible} now={now} />}
          {route === "settings" && (
            <Settings manager={manager} status={status} />
          )}
        </main>
        <footer className="workspace-footer">
          <span>
            <ShieldCheck size={14} aria-hidden="true" />
            CyberVisual · 边缘视觉设备
          </span>
          <span>
            <Move size={14} aria-hidden="true" />
            视频、事件与云台共享一个设备源
          </span>
        </footer>
      </div>
      <Drawer title="设备工作区" isOpen={navigationOpen} onOpenChange={setNavigationOpen}>
        {navigationLinks}
        <p className="drawer-note muted">CYBERVISUAL / EDGE VISION</p>
      </Drawer>
      <AppearanceDialog open={appearanceOpen} onOpenChange={setAppearanceOpen} />
    </div>
  );
}
