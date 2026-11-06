import { CircuitBoard, RefreshCw, Settings } from "lucide-react";

import { RuntimeStatusBar } from "../features/runtime/RuntimeStatusBar";
import type { RuntimeStatus } from "../features/runtime/types";

export function AppHeader({ status, onReloadStream, onOpenSettings }: {
  status: RuntimeStatus;
  onReloadStream: () => void;
  onOpenSettings: () => void;
}) {
  return (
    <header className="topbar">
      <div className="brand-lockup" aria-label="CyberVisual">
        <span className="brand-mark">CV</span>
        <span className="brand-divider" />
        <span className="brand-copy">
          <span className="brand-title">CyberVisual</span>
          <span className="brand-meta">
            <CircuitBoard size={11} aria-hidden="true" />
            <span>JETSON NANO</span>
            <i />
            <span>EDGE AI</span>
          </span>
        </span>
      </div>
      <div className="topbar-status">
        <RuntimeStatusBar status={status} />
        <button className="icon-button" type="button" aria-label="Reload stream" title="Reload stream" onClick={onReloadStream}>
          <RefreshCw size={18} />
        </button>
        <button className="icon-button" type="button" aria-label="Open settings" title="Open settings" onClick={onOpenSettings}>
          <Settings size={18} />
        </button>
      </div>
    </header>
  );
}
