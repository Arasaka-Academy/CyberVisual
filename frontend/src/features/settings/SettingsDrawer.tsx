import { Save, SlidersHorizontal } from "lucide-react";

import type { RuntimeConfig } from "./types";

export function SettingsDrawer({
  open,
  config,
  setConfig,
  onClose,
  onSave
}: {
  open: boolean;
  config: RuntimeConfig;
  setConfig: (config: RuntimeConfig) => void;
  onClose: () => void;
  onSave: () => void;
}) {
  function update<K extends keyof RuntimeConfig>(key: K, value: RuntimeConfig[K]) {
    setConfig({ ...config, [key]: value });
  }

  return (
    <aside className={`settings-drawer ${open ? "open" : ""}`} aria-hidden={!open} aria-label="Runtime settings">
      <div className="drawer-header">
        <div>
          <h2>Runtime</h2>
          <p>Camera, model, thresholds</p>
        </div>
        <button className="icon-button" type="button" aria-label="Close settings" title="Close settings" onClick={onClose}>
          <SlidersHorizontal size={18} />
        </button>
      </div>

      <label className="field">
        <span>Confidence</span>
        <input
          aria-label="Confidence"
          type="range"
          min="0"
          max="1"
          step="0.01"
          value={config.confidence}
          onChange={(event) => update("confidence", Number(event.target.value))}
        />
        <strong>{Math.round(config.confidence * 100)}%</strong>
      </label>

      <label className="field">
        <span>IOU</span>
        <input
          aria-label="IOU"
          type="range"
          min="0"
          max="1"
          step="0.01"
          value={config.iou}
          onChange={(event) => update("iou", Number(event.target.value))}
        />
        <strong>{Math.round(config.iou * 100)}%</strong>
      </label>

      <label className="field stacked">
        <span>Source</span>
        <select aria-label="Source" value={config.source} onChange={(event) => update("source", event.target.value as RuntimeConfig["source"])}>
          <option value="camera">USB camera</option>
          <option value="synthetic">Synthetic</option>
          <option value="video">Sample video</option>
        </select>
      </label>

      <label className="field stacked">
        <span>Detector</span>
        <select aria-label="Detector" value={config.detector_backend} onChange={(event) => update("detector_backend", event.target.value as RuntimeConfig["detector_backend"])}>
          <option value="auto">Auto</option>
          <option value="opencv">OpenCV DNN</option>
          <option value="tensorrt">TensorRT</option>
          <option value="mock">Mock</option>
        </select>
      </label>

      <label className="field stacked">
        <span>Model path</span>
        <input aria-label="Model path" value={config.model_path} onChange={(event) => update("model_path", event.target.value)} />
      </label>

      <label className="field stacked">
        <span>Class allowlist</span>
        <input
          aria-label="Class allowlist"
          value={config.class_allowlist.join(", ")}
          onChange={(event) =>
            update(
              "class_allowlist",
              event.target.value
                .split(",")
                .map((item) => item.trim())
                .filter(Boolean)
            )
          }
        />
      </label>

      <label className="toggle-field">
        <span>Auto person snapshot</span>
        <input
          aria-label="Auto person snapshot"
          type="checkbox"
          checked={config.auto_snapshot_enabled}
          onChange={(event) => update("auto_snapshot_enabled", event.target.checked)}
        />
      </label>

      <div className="resolution-row">
        <label className="field stacked">
          <span>Snapshot class</span>
          <input
            aria-label="Snapshot class"
            value={config.auto_snapshot_label}
            onChange={(event) => update("auto_snapshot_label", event.target.value)}
          />
        </label>
        <label className="field stacked">
          <span>Cooldown seconds</span>
          <input
            aria-label="Cooldown seconds"
            type="number"
            min="1"
            max="3600"
            value={config.auto_snapshot_cooldown_seconds}
            onChange={(event) => update("auto_snapshot_cooldown_seconds", Number(event.target.value))}
          />
        </label>
      </div>

      <div className="resolution-row">
        <label className="field stacked">
          <span>Width</span>
          <input
            aria-label="Width"
            type="number"
            min="160"
            max="3840"
            value={config.resolution.width}
            onChange={(event) => update("resolution", { ...config.resolution, width: Number(event.target.value) })}
          />
        </label>
        <label className="field stacked">
          <span>Height</span>
          <input
            aria-label="Height"
            type="number"
            min="120"
            max="2160"
            value={config.resolution.height}
            onChange={(event) => update("resolution", { ...config.resolution, height: Number(event.target.value) })}
          />
        </label>
      </div>

      <button className="primary-action" type="button" onClick={onSave}>
        <Save size={18} />
        <span>Save</span>
      </button>
    </aside>
  );
}
