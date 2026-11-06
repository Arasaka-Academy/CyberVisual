import { useEffect, useState } from "react";

import { captureSnapshot, getLatestDetections } from "../features/detections/api";
import type { Detection } from "../features/detections/types";
import { getStatus } from "../features/runtime/api";
import { emptyStatus, normalizeStatus } from "../features/runtime/model";
import type { RuntimeStatus } from "../features/runtime/types";
import { getConfig, updateConfig } from "../features/settings/api";
import { defaultConfig, normalizeConfig } from "../features/settings/model";
import type { RuntimeConfig } from "../features/settings/types";

export function useDashboard() {
  const [status, setStatus] = useState<RuntimeStatus>(emptyStatus);
  const [detections, setDetections] = useState<Detection[]>([]);
  const [config, setConfig] = useState<RuntimeConfig>(defaultConfig);
  const [notice, setNotice] = useState("");
  const [apiError, setApiError] = useState("");

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const [nextStatus, nextDetections] = await Promise.all([getStatus(), getLatestDetections()]);
        if (!cancelled) {
          setStatus(normalizeStatus(nextStatus));
          setDetections(nextDetections.detections);
          setApiError("");
        }
      } catch (error) {
        if (!cancelled) {
          setApiError(error instanceof Error ? error.message : "API unavailable");
        }
      }
    }

    load();
    const timer = window.setInterval(load, 1000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    getConfig()
      .then((nextConfig) => {
        if (!cancelled) {
          setConfig(normalizeConfig(nextConfig));
        }
      })
      .catch((error) => setApiError(error instanceof Error ? error.message : "Config unavailable"));
    return () => {
      cancelled = true;
    };
  }, []);

  const visibleError = apiError || status.last_error || status.auto_snapshot.last_error;

  async function saveSettings() {
    try {
      const next = await updateConfig(config);
      setConfig(next);
      setNotice("Settings saved");
      setApiError("");
      window.setTimeout(() => setNotice(""), 1800);
    } catch (error) {
      setApiError(error instanceof Error ? error.message : "Unable to save settings");
    }
  }

  async function saveSnapshot() {
    try {
      const result = await captureSnapshot();
      setNotice(`Snapshot saved: ${shortPath(result.image_path)}`);
      setApiError("");
      window.setTimeout(() => setNotice(""), 2600);
    } catch (error) {
      setApiError(error instanceof Error ? error.message : "Snapshot failed");
    }
  }

  return { status, detections, config, setConfig, notice, visibleError, saveSettings, saveSnapshot };
}

function shortPath(path: string) {
  return path.split("/").slice(-1)[0] || path;
}
