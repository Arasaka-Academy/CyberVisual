export type CameraEvent = {
  id: string;
  topic: string;
  source: string;
  category: string;
  state: boolean;
  frame_ts: number;
  initialized: boolean;
};
export type RecentEvents = {
  capacity: number;
  started_at: number;
  status: {
    online: boolean;
    presence: Record<string, boolean>;
    last_error: string | null;
    subscribers: number;
  };
  events: CameraEvent[];
};
