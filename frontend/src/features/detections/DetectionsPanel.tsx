import { Camera } from "lucide-react";

import type { Detection } from "./types";

export function DetectionsPanel({ detections, onSnapshot }: { detections: Detection[]; onSnapshot: () => void }) {
  return (
    <section className="panel detection-panel">
      <div className="panel-heading">
        <div>
          <h2>Detections</h2>
          <p>{detections.length} active objects</p>
        </div>
        <button className="icon-button compact" type="button" aria-label="Save snapshot" title="Save snapshot" onClick={onSnapshot}>
          <Camera size={17} />
        </button>
      </div>
      <div className="detection-list">
        {detections.length === 0 ? (
          <div className="empty-state">No objects above threshold</div>
        ) : (
          detections.map((item, index) => <DetectionRow key={`${item.label}-${index}`} detection={item} />)
        )}
      </div>
    </section>
  );
}

function DetectionRow({ detection }: { detection: Detection }) {
  const confidence = Math.round(detection.confidence * 100);
  return (
    <article className="detection-row">
      <div className="class-token">{detection.label.slice(0, 2).toUpperCase()}</div>
      <div>
        <h3>{detection.label}</h3>
        <p>
          x{detection.bbox.x1} y{detection.bbox.y1} · {detection.bbox.x2 - detection.bbox.x1}x{detection.bbox.y2 - detection.bbox.y1}
        </p>
      </div>
      <strong>{confidence}%</strong>
    </article>
  );
}
