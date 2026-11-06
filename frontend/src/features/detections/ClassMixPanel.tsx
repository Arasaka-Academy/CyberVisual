import { useMemo } from "react";

import type { Detection } from "./types";

export function ClassMixPanel({ detections }: { detections: Detection[] }) {
  const classStats = useMemo(() => {
    const counts = new Map<string, number>();
    detections.forEach((item) => counts.set(item.label, (counts.get(item.label) || 0) + 1));
    return Array.from(counts.entries()).sort((a, b) => b[1] - a[1]);
  }, [detections]);

  return (
    <section className="panel class-mix-panel">
      <div className="panel-heading">
        <div>
          <h2>Class Mix</h2>
          <p>Current frame distribution</p>
        </div>
      </div>
      <div className="class-bars">
        {classStats.length === 0 ? (
          <div className="empty-state">No classes detected</div>
        ) : (
          classStats.map(([label, count]) => (
            <div className="class-bar" key={label}>
              <span>{label}</span>
              <div className="bar-track">
                <div style={{ width: `${Math.max(18, (count / detections.length) * 100)}%` }} />
              </div>
              <strong>{count}</strong>
            </div>
          ))
        )}
      </div>
    </section>
  );
}
