// Hand-written TS mirrors of the backend Pydantic models — keep in sync in the same edit
// as backend/models/agrigaurd.py and the service response shapes.

export interface User {
  id: string;
  email: string;
  name: string;
  role: "FARMER" | "ADMIN" | "RESEARCHER";
}

export interface TokenOut {
  access_token: string;
  token_type: string;
  user: User;
}

export interface FieldDoc {
  id: string;
  user_id: string;
  name: string;
  state: string | null;
  district: string | null;
  village: string | null;
  latitude: number;
  longitude: number;
  boundary: { name: string; coordinates: number[][] };
  bbox: number[];
  area_ha: number;
  created_at: string;
  last_analysis: string | null;
  flood_status: string;
  flood_pct: number | null;
  flood_confidence: number | null;
  land_suitability: number | null;
  recommended_crop: string | null;
  monitoring: { enabled: boolean; frequency: string };
}

export interface EvidenceItem {
  icon: "ok" | "warn";
  text: string;
}

export interface ConfidenceFactor {
  value: number;
  note: string;
}

export interface Confidence {
  score: number;
  label: string;
  weights: Record<string, number>;
  factors: Record<string, ConfidenceFactor>;
  disclaimer: string;
}

export interface SarMetrics {
  available: boolean;
  reason?: string;
  valid_pixels?: number;
  water_after_pct?: number;
  water_before_pct?: number;
  new_water_pct?: number;
  water_expansion_pct?: number;
  vv_mean_before_db?: number;
  vv_mean_after_db?: number;
  vv_change_db?: number;
  vh_mean_before_db?: number;
  vh_change_db?: number;
  mean_backscatter_drop_new_water_db?: number;
}

export interface FloodBlock {
  status: string;
  total_water_pct: number | null;
  total_water_ha: number | null;
  new_water_pct: number | null;
  new_water_ha: number | null;
  agricultural_flood_pct: number | null;
  agricultural_flood_ha: number | null;
  flood_percentage: number;
  affected_ha: number;
  severity: "none" | "low" | "moderate" | "high" | "critical";
  severity_thresholds: Record<string, number>;
  confidence: Confidence;
  evidence: { positive: EvidenceItem[]; warnings: EvidenceItem[] };
  sar: SarMetrics;
  available: boolean;
  demo: boolean;
}

export interface SoilProperty {
  label: string;
  value: number;
  unit: string;
}

export interface SoilData {
  properties: Record<string, SoilProperty>;
  texture_class: { class: string; clay_pct: number; sand_pct: number } | null;
  source: string;
  resolution: string;
  depth: string;
}

export interface TerrainData {
  elevation_min_m: number;
  elevation_max_m: number;
  elevation_mean_m: number;
  elevation_range_m: number;
  slope_median_pct: number;
  low_lying_pct: number;
  terrain_risk: "low" | "moderate" | "high";
  sample_points: number;
  source: string;
  resolution: string;
}

export interface WeatherData {
  current: Record<string, unknown> | null;
  recent: {
    period_days: number;
    start_date: string;
    end_date: string;
    total_mm: number;
    last_7_days_mm: number;
    wet_days_10mm: number;
    max_daily_mm: number;
    daily: number[];
    dates: string[];
  };
  verdict: { level: string; statement: string; last_7_days_mm?: number; max_daily_mm?: number };
  source: string;
  resolution: string;
}

export interface Suitability {
  score: number;
  label: string;
  weights: Record<string, number>;
  factors: Record<string, { score: number | null; basis: string }>;
  excluded_factors: string[];
  rainfall_statement: string | null;
  disclaimer: string;
}

export interface CropFactor {
  factor: string;
  value: number | null;
  note: string;
}

export interface CropRec {
  crop: string;
  score: number;
  factors: CropFactor[];
  why: string[];
  risks: string[];
  duration_days: string;
  limits: string;
}

export interface CropsOut {
  season: string;
  month: number;
  methodology: string;
  recommendations: CropRec[];
}

export interface DataQuality {
  score: number;
  label: string;
  components: Record<string, { score: number; max: number }>;
  missing_sources: string[];
  note: string;
}

export interface AnalysisDoc {
  id: string;
  user_id: string;
  field_id: string | null;
  type: string;
  demo: boolean;
  boundary: { name: string; coordinates: number[][] };
  bbox: number[];
  area_ha: number;
  centroid: { lat: number; lng: number };
  state: string | null;
  district: string | null;
  village: string | null;
  before_window: { from: string; to: string } | null;
  after_window: { from: string; to: string } | null;
  discovery: Record<string, unknown>;
  images: { s1_before_png_b64: string | null; s1_after_png_b64: string | null };
  flood: FloodBlock;
  water_verification: {
    detected_water_pct: number | null;
    rivers_lakes: { nearby_waterways: number; nearby_water_bodies: number; verdict: string; note: string; names?: string[] };
    builtup: { building_count: number | null; road_count: number | null; verdict: string; note: string };
    landcover_water_pct: number | null;
    landcover_builtup_pct: number | null;
    sources: string[];
  };
  water_classification: {
    classification: string;
    permanent_pct: number | null;
    seasonal_pct: number | null;
    new_flood_pct: number | null;
    uncertain_pct: number | null;
    note: string;
  };
  landcover: {
    composition: Record<string, number> | null;
    cropland_pct: number | null;
    builtup_pct: number | null;
    water_pct: number | null;
    source: string | null;
    resolution: string | null;
    worldcover?: { status: string; error?: string };
    osm_landuse?: Record<string, unknown> | null;
  };
  soil: SoilData | null;
  soil_status: string;
  terrain: TerrainData | null;
  terrain_status: string;
  weather: WeatherData | null;
  weather_status: string;
  ndvi: { mean: number; min: number; max: number } | null;
  ndmi: { mean: number; min: number; max: number } | null;
  optical_note: string | null;
  vegetation_change: string | null;
  land_suitability: Suitability;
  crops: CropsOut;
  data_quality: DataQuality;
  analysis_date: string;
  status: string;
  message: string | null;
  sources: Record<string, string>;
  limitations: string[];
  created_at: string;
}

export interface JobStage {
  status: "pending" | "running" | "done";
  message: string;
  at: string | null;
}

export interface AnalysisJob {
  job_id: string;
  user_id: string;
  field_id: string | null;
  demo: boolean;
  state:
    | "QUEUED"
    | "FETCHING_DATA"
    | "PROCESSING"
    | "VERIFYING"
    | "GENERATING_RESULTS"
    | "COMPLETED"
    | "PARTIAL"
    | "FAILED";
  stages: Record<string, JobStage>;
  current_stage: string;
  created_at: string;
  updated_at: string;
  error?: string;
  analysis_id?: string;
  result_summary?: {
    flood_severity: string | null;
    agricultural_flood_pct: number | null;
    land_suitability: number | null;
    top_crop: string | null;
  };
}

export interface NotificationDoc {
  id: string;
  user_id: string;
  kind: string;
  severity: string;
  title: string;
  body: string;
  field_id: string | null;
  analysis_id: string | null;
  evidence: Record<string, unknown>;
  read: boolean;
  created_at: string;
}

export interface AlertPrefs {
  user_id: string;
  email_enabled: boolean;
  alert_email: string | null;
  sms_enabled: boolean;
  alert_phone: string | null;
  min_severity: string;
  updated_at?: string;
}

export interface MonitoringConfig {
  id?: string;
  user_id?: string;
  field_id?: string;
  frequency: "daily" | "every_3_days" | "weekly";
  enabled: boolean;
  next_run?: string;
  last_run?: string | null;
}

export interface CompareMetrics {
  [key: string]: number | string | null;
  agricultural_flood_pct: number | null;
  affected_ha: number | null;
  total_water_pct: number | null;
  confidence: number | null;
  ndvi: number | null;
  ndmi: number | null;
  land_suitability: number | null;
  crop_score: number | null;
  crop: string | null;
}

export interface CompareOut {
  base: { id: string; date: string; metrics: CompareMetrics };
  other: { id: string; date: string; metrics: CompareMetrics };
  deltas: Record<string, { absolute: number | null; pct: number | null; direction: string }>;
}

export interface HealthCheck {
  service: string;
  status: "CONNECTED" | "NOT CONFIGURED" | "ERROR" | "OPTIONAL";
  detail: string;
}

export interface HealthOut {
  checks: HealthCheck[];
  backend: { status: string; detail: string };
  configured: { sentinel_hub: boolean; llm: boolean; email: boolean; sms: boolean };
  checked_at: string;
  note: string;
}

export interface AdminOverview {
  counts: Record<string, number>;
  users_over_time: { month: string; count: number }[];
  analyses_over_time: { month: string; count: number }[];
  flood_severity: { severity: string; count: number }[];
  crop_recommendations: { crop: string; count: number; avg_score: number }[];
  recent_errors: { event: string; detail: Record<string, unknown>; created_at: string }[];
  generated_at: string;
}

export interface Observation {
  satellite: string;
  id?: string;
  acquired: string | null;
  cloud_pct?: number | null;
  orbit?: string | null;
  quality: string;
}

export interface DiscoverOut {
  sentinel_hub_configured: boolean;
  observations: Observation[];
  latest_available?: string | null;
  message?: string;
  note?: string;
}

export interface GeocodeResult {
  display_name: string;
  lat: number;
  lng: number;
  type: string | null;
}

export interface CropKBEntry {
  name: string;
  ph_min: number;
  ph_max: number;
  texture: string[];
  moisture_need: string;
  flood_tolerance: number;
  temp_min: number;
  temp_max: number;
  seasons: string[];
  regions: string[];
  duration_days: string;
  limits: string;
}

// --- Sowing calendar (mirrors backend/services/sowing_service.py) ---
export interface SowingMonth {
  month: number;
  label: string;
  verdict: string;
  reason: string;
}

export interface SowingFactor {
  state: string;
  note: string;
  wait_days?: number;
}

export interface SowingCrop {
  crop: string;
  score: number | null;
  seasons: string[];
  duration_days: string;
  flood_tolerance: number;
  moisture_need: string;
  months: SowingMonth[];
  sow_window: string[];
  current_verdict: string;
  current_reason: string;
  drainage_wait_days: number;
  factors: { moisture: SowingFactor; flood: SowingFactor; limits: string };
}

export interface SowingCalendarOut {
  field_id: string | null;
  field_name: string | null;
  analysis_id: string | null;
  analysis_date: string | null;
  month: number;
  month_label: string;
  season: string;
  rainfall: {
    last_7_days_mm: number | null;
    last_30_days_mm: number | null;
    forecast_precip_mm: number | null;
    available: boolean;
    source: string | null;
  };
  flood_severity: string | null;
  flood_verified?: boolean;
  agricultural_flood_pct: number | null;
  crops: SowingCrop[];
  methodology: string;
  limitations: string[];
}

// --- Village compare (mirrors backend/services/village_service.py) ---
export interface VillageAgg {
  count: number;
  average: number | null;
  median: number | null;
  min: number | null;
  max: number | null;
  your_value: number | null;
  your_percentile: number | null;
}

export interface VillagePeer {
  distance_km: number;
  own_field: boolean;
  name: string;
  field_id: string | null;
  area_ha: number | null;
  district: string | null;
  state: string | null;
  flood_pct: number | null;
  land_suitability: number | null;
  recommended_crop: string | null;
  analysed: boolean;
}

export interface VillageCompareOut {
  status: string;
  radius_km: number;
  field?: {
    id: string;
    name: string | null;
    flood_pct: number | null;
    land_suitability: number | null;
    recommended_crop: string | null;
    district: string | null;
    state: string | null;
  };
  neighbour_count: number;
  analysed_neighbour_count: number;
  flood: VillageAgg;
  suitability: VillageAgg;
  popular_crops: { crop: string; fields: number }[];
  peers: VillagePeer[];
  verdicts: string[];
  privacy: string;
}
