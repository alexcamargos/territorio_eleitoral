/**
 * TypeScript contracts mirroring `docs/08-api.md` and `src/territorio/api/repository.py`.
 */

export type OfficeCode =
  | "president"
  | "governor"
  | "senator"
  | "federal_deputy"
  | "state_deputy"
  | "district_deputy"
  | "state_or_district_deputy";

export type BlocCode = "left" | "center" | "right";

export type ThemeCode =
  | "economy"
  | "transfers"
  | "social"
  | "education"
  | "health"
  | "infrastructure"
  | "fiscal"
  | "composite"
  | "electoral";

export type ScaleHintCode =
  | "linear"
  | "log"
  | "quantile"
  | "ordinal"
  | "categorical";

export type ValueTypeCode = "continuous" | "ordinal" | "categorical";

export type HigherIsCode = "better" | "worse" | "neutral";

export type StoryStep = 1 | 2 | 3 | 4;

export type MapLayerMode =
  | "electoral_balance"
  | "electoral_bloc"
  | "indicator";

export type GeoLevel = "state" | "municipality";

export type ThemeMode = "light" | "dark";

export interface HealthResponse {
  status: string;
  postgis_version: string;
  dataset_version: number | null;
  published_at: string | null;
  municipality_count: number;
}

export interface DefaultSelection {
  year: number;
  round: 1 | 2;
  office: OfficeCode;
  bloc: BlocCode;
  indicator: string;
}

export interface ElectionMeta {
  id: number;
  year: number;
  round: 1 | 2;
  office: OfficeCode;
  office_label: string;
  system: "majoritarian" | "proportional";
  scope: "national" | "state" | "municipal";
  votes_per_voter: number;
  election_date: string | null;
  source_version: string | null;
}

export interface IndicatorMeta {
  code: string;
  label: string;
  description: string;
  theme: ThemeCode;
  theme_label: string;
  tier: 1 | 2 | 3;
  unit: string;
  value_type: ValueTypeCode;
  higher_is: HigherIsCode;
  scale_hint: ScaleHintCode;
  ref_year: number | null;
  coverage: number;
  source_name: string;
  source_url: string | null;
  caveat: string | null;
}

export interface UfMeta {
  uf: string;
  name: string;
  region: string;
  bbox: [number, number, number, number];
}

export interface PartyIdeologyMeta {
  party_code: string;
  score: number;
  bloc: BlocCode;
  method: "survey" | "derived" | "manual";
  source: string;
}

export interface MetaResponse {
  dataset_version: number;
  default_selection: DefaultSelection;
  elections: ElectionMeta[];
  indicators: IndicatorMeta[];
  ufs: UfMeta[];
  party_ideology: PartyIdeologyMeta[];
}

/**
 * Row tuple in `GET /api/v1/elections/{year}/{office}/{round}/map` (municipal):
 * `[cd_ibge, left_share, center_share, right_share, lr_balance, leading_bloc, valid_votes]`
 */
export type ElectionMapRow = readonly [
  number,
  number,
  number,
  number,
  number,
  BlocCode,
  number,
];

/**
 * Row tuple in `GET /api/v1/elections/.../map?level=uf` (UF level):
 * `[uf, uf_code, name, left_share, center_share, right_share, lr_balance, leading_bloc, valid_votes, turnout_pct, leading_share]`
 */
export type ElectionUfMapRow = readonly [
  string,
  number,
  string,
  number,
  number,
  number,
  number,
  BlocCode,
  number,
  number,
  number,
];

export interface ElectionNationalSummary {
  eligible: number;
  attendance: number;
  valid_votes: number;
  abroad_valid_votes: number;
  bloc_shares: Record<BlocCode, number>;
  municipalities_won: Record<BlocCode, number>;
  ufs_won?: Record<BlocCode, number>;
}

export interface ElectionMapResponse {
  election: {
    year: number;
    office: OfficeCode;
    round: 1 | 2;
  };
  level?: "uf" | "municipality";
  national_summary: ElectionNationalSummary;
  quantiles: {
    lr_balance: number[];
    left_share: number[];
    center_share?: number[];
    right_share: number[];
  };
  columns: readonly string[];
  rows: (ElectionMapRow | ElectionUfMapRow)[];
}

/**
 * Row tuple in `GET /api/v1/indicators/{code}/map` (municipal):
 * `[cd_ibge, value]` where `value` can be numeric, categorical text, or null.
 */
export type IndicatorMapRow = readonly [number, number | string | null];

/**
 * Row tuple in `GET /api/v1/indicators/{code}/map?level=uf`:
 * `[uf, uf_code, name, value]`
 */
export type IndicatorUfMapRow = readonly [
  string,
  number,
  string,
  number | null,
];

export interface IndicatorSummary {
  count_valid: number;
  count_missing: number;
  min: number | null;
  p10: number | null;
  p25: number | null;
  median: number | null;
  p75: number | null;
  p90: number | null;
  max: number | null;
  quantiles_7: number[];
}

export interface IndicatorMapResponse {
  indicator: {
    code: string;
    label: string;
    unit: string;
    ref_year: number;
    scale_hint: ScaleHintCode;
    source_name: string;
    caveat: string | null;
  };
  level?: "uf" | "municipality";
  summary: IndicatorSummary;
  columns: readonly string[];
  rows: (IndicatorMapRow | IndicatorUfMapRow)[];
}

export type CorrelationStrengthCode =
  | "negligible"
  | "weak"
  | "moderate"
  | "strong"
  | "very_strong";

export type CorrelationDirectionCode = "positive" | "negative" | "neutral";

export interface CorrelationPayload {
  spearman_rho: number;
  spearman_p: number;
  pearson_r: number;
  pearson_p: number;
  strength: CorrelationStrengthCode;
  strength_label: string;
  direction: CorrelationDirectionCode;
  direction_label: string;
}

export interface TrendlinePayload {
  model: "linear" | "log10";
  points: [number, number][];
}

export interface DecilePayload {
  decile: number;
  municipality_count: number;
  indicator_min: number;
  indicator_max: number;
  indicator_median: number;
  valid_votes: number;
  bloc_votes: number;
  weighted_share: number;
  unweighted_mean_share: number;
}

/**
 * Scatter row tuple:
 * Municipal: `[cd_ibge, x, y, valid_votes, region]`
 * UF: `[uf, uf_code, name, x, y, valid_votes, region]`
 */
export type ScatterRow =
  | readonly [number, number, number, number, string]
  | readonly [string, number, string, number, number, number, string];

export type InsightSeverity = "headline" | "finding" | "caveat";

export interface InsightCardPayload {
  template_id: string;
  severity: InsightSeverity;
  title: string;
  text: string;
  params: Record<string, number | string>;
}

export interface QuintileExtremesContrast {
  bottom_quintile_share: number;
  top_quintile_share: number;
  diff_pp: number;
  bottom_indicator_range: [number, number];
  top_indicator_range: [number, number];
  bottom_municipality_count: number;
  top_municipality_count: number;
  tipping_point_decile: number | null;
  tipping_point_threshold: number | null;
}

export interface StoryTrack {
  id: string;
  icon: string;
  title: string;
  short_title: string;
  theme: string;
  question: string;
  description: string;
  preset: {
    year: number;
    round: 1 | 2;
    office: OfficeCode;
    bloc: BlocCode;
    indicator: string;
    uf: string | null;
  };
}

export interface AnalysisResponse {
  scope: {
    year: number;
    office: OfficeCode;
    round: 1 | 2;
    bloc: BlocCode;
    uf: string | null;
  };
  indicator: {
    code: string;
    label: string;
    unit: string;
    ref_year: number;
    scale_hint: ScaleHintCode;
    caveat: string | null;
  };
  sample: {
    total_municipalities: number;
    valid_pairs: number;
    missing_pairs: number;
  };
  correlation: CorrelationPayload;
  trendline: TrendlinePayload;
  deciles: DecilePayload[];
  extremes_contrast?: QuintileExtremesContrast | null;
  scatter: {
    columns: readonly ["cd_ibge", "x", "y", "valid_votes", "region"];
    rows: ScatterRow[];
  };
  insights: InsightCardPayload[];
}

export interface MunicipalitySearchItem {
  cd_ibge: number;
  name: string;
  uf: string;
  region: string;
  bbox: [number, number, number, number] | number[];
}

export interface MunicipalitySearchResponse {
  items: MunicipalitySearchItem[];
}

export interface CandidateVoteItem {
  ballot_name: string;
  party_code: string;
  bloc: BlocCode;
  votes: number;
  share: number;
}

export interface MunicipalityOfficeResult {
  turnout: {
    eligible: number;
    attendance: number;
    valid: number;
    turnout_pct: number;
    blank_null_pct: number;
  };
  bloc_shares: Record<BlocCode, number>;
  top_candidates: CandidateVoteItem[];
}

export interface MunicipalityIndicatorItem {
  code: string;
  label: string;
  value: number | string | null;
  unit: string;
  ref_year: number;
  national_percentile: number | null;
}

export interface MunicipalityProfileResponse {
  municipality: {
    cd_ibge: number;
    name: string;
    uf: string;
    region: string;
    is_capital: boolean;
    area_km2: number;
    bbox: [number, number, number, number] | number[];
  };
  elections: Record<string, MunicipalityOfficeResult>;
  indicators: MunicipalityIndicatorItem[];
}

export interface ApiErrorEnvelope {
  error: {
    code: string;
    message: string;
    details?: Record<string, unknown>;
  };
}
