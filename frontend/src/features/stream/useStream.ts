import { useState } from "react";

import { API_BASE } from "../../shared/api";

export function useStream() {
  const [streamKey, setStreamKey] = useState(0);
  const [streamError, setStreamError] = useState(false);

  return {
    streamUrl: `${API_BASE}/stream.mjpg?view=${streamKey}`,
    streamError,
    onLoad: () => setStreamError(false),
    onError: () => setStreamError(true),
    reloadStream: () => setStreamKey((value) => value + 1)
  };
}
