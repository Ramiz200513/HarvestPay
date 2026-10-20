// Типы повторяют Pydantic-схемы бэкенда (backend/app/schemas.py).
// Если меняете схему на сервере — поправьте и здесь, иначе TypeScript не подскажет об ошибке.

export type LngLat = [number, number]; // GeoJSON: [долгота, широта]

export interface GeoPolygon {
  type: "Polygon";
  coordinates: LngLat[][];
}

export interface Farm {
  bin: string;
  name: string | null;
  legal_form: string | null;
  registered_at: string | null;
  status: "verified" | "rejected";
  reasons: string[];
  source: string | null;
}

export interface Product {
  id: number;
  name: string;
  category: "seeds" | "fertilizer" | "protection";
  supplier: string;
  unit: string;
  price: number;
}

export type ApplicationStatus = "pending" | "processing" | "approved" | "review" | "rejected" | "error";

export interface Season {
  year: number;
  ndvi_peak: number | null;
  ndvi_mean: number | null;
  soil_moisture: number | null;
  scenes: number;
}

export interface Payment {
  date: string;
  amount: number;
}

export interface Decision {
  score: number | null;
  score_class: "A" | "B" | "C";
  components: {
    mean_ndvi?: number;
    mean_norm?: number;
    volatility_cv?: number;
    volatility_norm?: number;
    trend_slope?: number;
    trend_norm?: number;
    moisture_penalty?: number;
  };
  reasons: string[];
  limit_amount: number;
  approved_amount: number;
  schedule: Payment[];
  decided_by: "auto" | "analyst";
  analyst_comment: string | null;
}

// Пересечение с полем другого хозяйства. farm_name/farm_bin/geometry приходят только аналитику.
export interface Overlap {
  overlap_ha: number;
  share: number; // 0..1 — доля от меньшего из двух полей
  other_area_ha: number;
  farm_name: string | null;
  farm_bin: string | null;
  geometry: GeoPolygon | null;
}

export interface FieldCheck {
  area_ha: number;
  overlaps: Overlap[];
}

export interface ApplicationItem {
  product_id: number;
  name: string;
  unit: string;
  quantity: number;
  price: number;
  total: number;
}

export interface Application {
  id: string;
  status: ApplicationStatus;
  error_message: string | null;
  created_at: string;
  updated_at: string;
  requested_amount: number;
  farm: Farm;
  field: {
    geometry: GeoPolygon;
    crop: string;
    area_ha: number;
    centroid_lat: number;
    centroid_lon: number;
  };
  items: ApplicationItem[];
  seasons: Season[];
  decision: Decision | null;
  overlaps: Overlap[];
}

export interface ApplicationListItem {
  id: string;
  status: ApplicationStatus;
  created_at: string;
  farm_name: string | null;
  bin: string;
  area_ha: number;
  crop: string;
  requested_amount: number;
  score: number | null;
  score_class: "A" | "B" | "C" | null;
  has_overlaps: boolean;
}

export interface PublicConfig {
  satellite_provider: "mock" | "gee";
  registry_provider: "mock" | "statgov";
  seasons: number;
  limit_per_ha: number;
}
