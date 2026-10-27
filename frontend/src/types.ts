// Типы повторяют Pydantic-схемы бэкенда (backend/app/schemas.py).
// Если меняете схему на сервере — поправьте и здесь, иначе TypeScript не подскажет об ошибке.

export type LngLat = [number, number]; // GeoJSON: [долгота, широта]

export interface GeoPolygon {
  type: "Polygon";
  coordinates: LngLat[][];
}

export interface Check {
  label: string;
  status: "ok" | "warn" | "fail" | "info";
  detail: string;
}

export interface Farm {
  bin: string;
  name: string | null;
  legal_form: string | null;
  registered_at: string | null;
  status: "verified" | "rejected";
  reasons: string[];
  source: string | null;
  checks: Check[];
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
  frost_days: number | null;
  heat_days: number | null;
}

export interface Payment {
  date: string;
  amount: number;
  note?: string | null;
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
    frost_days_avg?: number | null;
    heat_days_avg?: number | null;
    climate_penalty?: number;
    field_class?: "A" | "B" | "C";
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

export type DealStatus =
  | "contracted"
  | "supplier_paid"
  | "delivered"
  | "sowing_confirmed"
  | "restructured"
  | "repaid";

export type DealAction = "pay_supplier" | "confirm_delivery" | "confirm_sowing" | "record_payment" | "restructure";

export interface Economics {
  goods_amount: number;
  discount_income: number;
  supplier_payout: number;
  fee_income: number;
  farmer_total: number;
  funding_days: number;
  funding_cost: number;
  expected_loss: number;
  margin: number;
  margin_pct: number;
}

export interface FlowStep {
  when: string;
  source: string;
  target: string;
  amount: number;
  kind: "money" | "goods";
  note: string;
}

export interface ScenarioRow {
  loss: number;
  from_farmer: number;
  insurance: number;
  rollover: number;
  platform_result: number;
  rollover_uninsured: number;
  platform_result_uninsured: number;
}

export interface NdviPoint {
  date: string;
  ndvi: number;
}

export interface Monitoring {
  season: number;
  status: "no_data" | "waiting" | "not_sown" | "growing" | "normal" | "stress";
  message: string;
  note: string | null;
  norm_peak: number;
  points: NdviPoint[];
  expected: NdviPoint[];
  sown_on: string | null;
  peak: number | null;
  ratio: number | null;
  estimated_loss: number | null;
  checked_at: string;
  source: string;
}

export interface Deal {
  status: DealStatus;
  overdue: boolean;
  score_class: "A" | "B" | "C";
  goods_amount: number;
  farmer_total: number;
  paid_amount: number;
  schedule: Payment[];
  payout_date: string;
  events: { at: string; action: string; amount: number | null; note: string }[];
  // только аналитику — у фермера null
  economics: Economics | null;
  discount_rate: number | null;
  fee_rate: number | null;
  funding_rate: number | null;
  flow: FlowStep[] | null;
  scenario: ScenarioRow[] | null;
  monitoring: Monitoring | null;
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
    cadastral_number: string | null;
    area_ha: number;
    centroid_lat: number;
    centroid_lon: number;
  };
  items: ApplicationItem[];
  seasons: Season[];
  decision: Decision | null;
  overlaps: Overlap[];
  deal: Deal | null;
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
  deal_status: DealStatus | null;
}

export interface PortfolioDeal {
  application_id: string;
  farm_name: string | null;
  crop: string;
  area_ha: number;
  score_class: "A" | "B" | "C";
  status: DealStatus;
  overdue: boolean;
  goods_amount: number;
  farmer_total: number;
  paid_amount: number;
  margin: number;
  monitoring_status: Monitoring["status"] | null;
}

export interface Portfolio {
  credit_line: { bank: string; limit: number; used: number; available: number; rate: number };
  deals_count: number;
  goods_amount: number;
  supplier_payout: number;
  farmer_total: number;
  paid_amount: number;
  expected_margin: number;
  expected_loss: number;
  by_status: Partial<Record<DealStatus, number>>;
  by_class: Partial<Record<"A" | "B" | "C", number>>;
  upcoming: Payment[];
  deals: PortfolioDeal[];
}

export interface PublicConfig {
  satellite_provider: "mock" | "gee" | "cdse";
  climate_provider: "openmeteo" | "off";
  registry_provider: "mock" | "statgov";
  seasons: number;
  limit_per_ha: number;
  max_limit_a: number;
}
