import { useState } from "react";

import { ClassMixPanel } from "../features/detections/ClassMixPanel";
import { DetectionsPanel } from "../features/detections/DetectionsPanel";
import { NetworkCameraPanel } from "../features/network-camera/NetworkCameraPanel";
import { RuntimeMetrics } from "../features/runtime/RuntimeMetrics";
import { SystemPanel } from "../features/runtime/SystemPanel";
import { SettingsDrawer } from "../features/settings/SettingsDrawer";
import { StreamPreview } from "../features/stream/StreamPreview";
import { useStream } from "../features/stream/useStream";
import { AppHeader } from "./AppHeader";
import { NotificationToast } from "./NotificationToast";
import { useDashboard } from "./useDashboard";

export default function App() {
  const { status, detections, config, setConfig, notice, visibleError, saveSettings, saveSnapshot } = useDashboard();
  const [settingsOpen, setSettingsOpen] = useState(false);
  const { reloadStream, ...stream } = useStream();

  return (
    <main className="app-shell">
      <AppHeader status={status} onReloadStream={reloadStream} onOpenSettings={() => setSettingsOpen(true)} />
      <section className="workspace">
        <section className="video-column" aria-label="Live detection stream">
          <StreamPreview status={status} resolution={config.resolution} {...stream} />
          <RuntimeMetrics status={status} />
        </section>
        <aside className="inspector" aria-label="Detection inspector">
          <DetectionsPanel detections={detections} onSnapshot={saveSnapshot} />
          <ClassMixPanel detections={detections} />
          <SystemPanel status={status} config={config} />
          <NetworkCameraPanel camera={status.network_camera} />
        </aside>
      </section>
      <NotificationToast notice={notice} error={visibleError} />
      <SettingsDrawer
        open={settingsOpen}
        config={config}
        setConfig={setConfig}
        onClose={() => setSettingsOpen(false)}
        onSave={saveSettings}
      />
    </main>
  );
}
