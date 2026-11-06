import { Camera } from "lucide-react";

import type { NetworkCameraStatus } from "./types";

export function NetworkCameraPanel({ camera }: { camera?: NetworkCameraStatus }) {
  return (
    <section className="panel network-camera-panel" aria-label="Network camera connection">
      <div className="panel-heading">
        <div>
          <h2>Network Camera</h2>
          <p>{camera?.enabled ? camera.state : "Disabled"}</p>
        </div>
        <Camera size={18} aria-hidden="true" />
      </div>
      {camera?.enabled ? (
        <>
          <dl className="system-list">
            <div><dt>Access</dt><dd>{camera.credentials_configured ? "Account configured" : "Account required"}</dd></div>
            <div><dt>Encoder</dt><dd>{camera.encoder || "Unavailable"}</dd></div>
            <div><dt>Discovery</dt><dd>{camera.discovery.state}</dd></div>
            <div><dt>AI events</dt><dd>{camera.events.online ? "Online" : "Offline"}</dd></div>
            <div><dt>PTZ</dt><dd>{camera.ptz.last_error ? "Unavailable" : camera.ptz.simulated ? "Simulated" : camera.ptz.enabled ? "Enabled" : "Disabled"}</dd></div>
          </dl>
          <div className="protocol-endpoints">
            {camera.onvif_url && <div><span>ONVIF</span><code>{camera.onvif_url}</code></div>}
            {camera.profiles.map((profile) => profile.rtsp_uri && (
              <div key={profile.token}>
                <span>{profile.name} · {profile.active ? "Streaming" : "Idle"}</span>
                <code>{profile.rtsp_uri}</code>
                {profile.last_error && <p className="protocol-error" role="status">{profile.last_error}</p>}
              </div>
            ))}
          </div>
          {(camera.last_error || camera.discovery.last_error || camera.events.last_error || camera.ptz.last_error) && (
            <p className="protocol-error" role="status">{camera.last_error || camera.discovery.last_error || camera.events.last_error || camera.ptz.last_error}</p>
          )}
        </>
      ) : <p className="protocol-help">Enable network camera output in the device configuration to connect a camera manager.</p>}
    </section>
  );
}
