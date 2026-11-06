export type BBox = {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
};

export type Detection = {
  label: string;
  confidence: number;
  bbox: BBox;
  frame_ts: number;
  class_id?: number;
};

export type LatestDetectionsResponse = {
  frame_ts: number | null;
  version: number;
  detections: Detection[];
};
