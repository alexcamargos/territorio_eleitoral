/**
 * Chromatic governance (ADR-006), colorblind-safe choropleth ramps,
 * and MapLibre `feature-state` expression builders (`docs/10-design-system.md` §2.2).
 */

import type {
  BlocCode,
  IndicatorMapRow,
  MapLayerMode,
  ThemeCode,
  ThemeMode,
  ValueTypeCode,
} from "../types/api";

export interface ThemeMapColors {
  background: string;
  noData: string;
  munStroke: string;
  ufStroke: string;
  hoverStroke: string;
}

export function getThemeMapColors(theme: ThemeMode): ThemeMapColors {
  if (theme === "dark") {
    return {
      background: "#0A0E14",
      noData: "#2A3241",
      munStroke: "rgba(241, 245, 249, 0.14)",
      ufStroke: "rgba(241, 245, 249, 0.55)",
      hoverStroke: "#F8FAFC",
    };
  }
  return {
    background: "#EAE6DF",
    noData: "#D6D3CD",
    munStroke: "rgba(22, 24, 29, 0.14)",
    ufStroke: "rgba(22, 24, 29, 0.55)",
    hoverStroke: "#16181D",
  };
}

export function getScatterCanvasColors(
  theme: ThemeMode,
  bloc: BlocCode,
): {
  pointFill: string;
  pointStroke: string;
  activeFill: string;
  gridLine: string;
} {
  const isDark = theme === "dark";
  const blocMap: Record<BlocCode, string> = isDark
    ? {
        left: "rgba(239, 68, 68, 0.55)",
        center: "rgba(245, 158, 11, 0.55)",
        right: "rgba(59, 130, 246, 0.55)",
      }
    : {
        left: "rgba(200, 62, 49, 0.55)",
        center: "rgba(217, 119, 6, 0.55)",
        right: "rgba(37, 99, 235, 0.55)",
      };
  return {
    pointFill: blocMap[bloc],
    pointStroke: isDark ? "rgba(241, 245, 249, 0.25)" : "rgba(22, 24, 29, 0.22)",
    activeFill: isDark ? "#14B8A6" : "#0F766E",
    gridLine: isDark ? "rgba(148, 163, 184, 0.16)" : "rgba(74, 80, 92, 0.14)",
  };
}

export type ColorRamp7 = readonly [
  string,
  string,
  string,
  string,
  string,
  string,
  string,
];

/**
 * Canonical 7-step colorblind-safe palettes from `docs/10-design-system.md` §2.2.
 * Note: Red/Terracotta and Blue/Cobalt are reserved strictly for electoral vote layers.
 */
export const PALETTES: Record<
  | "DivergingLeftRight"
  | "SequentialLeft"
  | "SequentialRight"
  | "SequentialCenter"
  | "SequentialTeal"
  | "SequentialAmberPurple"
  | "SequentialEmerald",
  ColorRamp7
> = {
  DivergingLeftRight: [
    "#8C1D18",
    "#C83E31",
    "#E9958C",
    "#F2EFE9",
    "#8EB8F7",
    "#2563EB",
    "#172E6E",
  ],
  SequentialLeft: [
    "#FDF2F0",
    "#F7D1CB",
    "#EBA197",
    "#DC6D60",
    "#C83E31",
    "#9E251B",
    "#6E140E",
  ],
  SequentialRight: [
    "#EFF6FF",
    "#C7DDFB",
    "#93C5FD",
    "#5496F9",
    "#2563EB",
    "#1D4ED8",
    "#172E6E",
  ],
  SequentialCenter: [
    "#FFFBEB",
    "#FDE68A",
    "#FBBF24",
    "#F59E0B",
    "#D97706",
    "#B45309",
    "#78350F",
  ],
  SequentialTeal: [
    "#F0F9E8",
    "#CCEBC5",
    "#A8DDB5",
    "#7BCCC4",
    "#4EB3D3",
    "#2B8CBE",
    "#08589E",
  ],
  SequentialAmberPurple: [
    "#FCFBFD",
    "#EFEDF5",
    "#DADAEB",
    "#BCBDDC",
    "#9E9AC8",
    "#756BB1",
    "#4A1486",
  ],
  SequentialEmerald: [
    "#ECFDF5",
    "#D1FAE5",
    "#A7F3D0",
    "#6EE7B7",
    "#34D399",
    "#059669",
    "#064E3B",
  ],
};

/**
 * Returns the 7-step electoral palette for the active map layer mode and bloc.
 */
export function getElectoralPalette(
  mode: Exclude<MapLayerMode, "indicator">,
  bloc: BlocCode,
): ColorRamp7 {
  if (mode === "electoral_balance") {
    return PALETTES.DivergingLeftRight;
  }
  if (bloc === "left") {
    return PALETTES.SequentialLeft;
  }
  if (bloc === "center") {
    return PALETTES.SequentialCenter;
  }
  return PALETTES.SequentialRight;
}

/**
 * Returns the 7-step indicator palette for a given `ThemeCode`.
 * Strictly enforces ADR-006: never returns `DivergingLeftRight`, `SequentialLeft`, or `SequentialRight`.
 */
export function getIndicatorPalette(theme: ThemeCode): ColorRamp7 {
  switch (theme) {
    case "transfers":
    case "social":
    case "electoral":
      return PALETTES.SequentialAmberPurple;
    case "fiscal":
      return PALETTES.SequentialEmerald;
    case "economy":
    case "education":
    case "health":
    case "infrastructure":
    case "composite":
    default:
      return PALETTES.SequentialTeal;
  }
}

export interface LegendBin {
  index: number;
  min: number;
  max: number;
  color: string;
  labelOverride?: string;
}

/**
 * Builds 6 inner threshold stops from either an 8-element `quantiles_7` array
 * (`[min, q1, q2, q3, q4, q5, q6, max]`), a 6-element threshold array, or a 5-element array.
 */
export function normalizeThresholdsTo6(rawQuantiles: readonly number[]): number[] {
  if (rawQuantiles.length === 8) {
    return rawQuantiles.slice(1, 7);
  }
  if (rawQuantiles.length === 6) {
    return [...rawQuantiles];
  }
  if (rawQuantiles.length === 5) {
    const first = rawQuantiles[0] ?? 0;
    const second = rawQuantiles[1] ?? first + 0.1;
    const mid = (first + second) / 2;
    return [first, mid, ...rawQuantiles.slice(1)];
  }
  if (rawQuantiles.length >= 2) {
    const min = rawQuantiles[0] ?? 0;
    const max = rawQuantiles[rawQuantiles.length - 1] ?? 1;
    const span = max - min || 1;
    return [1, 2, 3, 4, 5, 6].map((i) => min + (span * i) / 7);
  }
  return [-0.5, -0.25, -0.08, 0.08, 0.25, 0.5];
}

/**
 * Resolves the 7-bin palette color for a single numeric metric value.
 */
export function getColorForMetricValue(
  value: number | null | undefined,
  thresholds: readonly number[],
  palette: ColorRamp7,
  noDataColor: string,
): string {
  if (value === null || value === undefined || isNaN(value)) {
    return noDataColor;
  }
  const stops6 = normalizeThresholdsTo6(thresholds);
  if (value < (stops6[0] ?? 0)) return palette[0];
  if (value < (stops6[1] ?? 0)) return palette[1];
  if (value < (stops6[2] ?? 0)) return palette[2];
  if (value < (stops6[3] ?? 0)) return palette[3];
  if (value < (stops6[4] ?? 0)) return palette[4];
  if (value < (stops6[5] ?? 0)) return palette[5];
  return palette[6];
}

/**
 * Builds a MapLibre `case` + `step` expression coloring polygons by `["feature-state", "metric"]`.
 * Polygons with `metric === null` receive `noDataColor`.
 */
export function buildMapLibreColorExpression(
  thresholds: readonly number[],
  palette: ColorRamp7,
  noDataColor: string,
): unknown[] {
  const stops6 = normalizeThresholdsTo6(thresholds);
  // Ensure strictly ascending thresholds for MapLibre `step`
  const safeStops: number[] = [];
  for (let i = 0; i < 6; i++) {
    const val = stops6[i] ?? i;
    const prev = i > 0 ? (safeStops[i - 1] ?? val - 1e-5) : val - 1;
    safeStops.push(val <= prev ? prev + 1e-5 : val);
  }

  return [
    "case",
    ["==", ["feature-state", "metric"], null],
    noDataColor,
    [
      "step",
      ["to-number", ["feature-state", "metric"]],
      palette[0],
      safeStops[0],
      palette[1],
      safeStops[1],
      palette[2],
      safeStops[2],
      palette[3],
      safeStops[3],
      palette[4],
      safeStops[4],
      palette[5],
      safeStops[5],
      palette[6],
    ],
  ];
}

/**
 * Builds the 7 legend bins from `quantiles_7` (8 boundary values) or 6 inner stops + domain bounds.
 */
export function buildLegendBins(
  boundariesOrStops: readonly number[],
  palette: ColorRamp7,
  domainMin?: number,
  domainMax?: number,
): LegendBin[] {
  let bounds8: number[];
  if (boundariesOrStops.length === 8) {
    bounds8 = [...boundariesOrStops];
  } else {
    const stops6 = normalizeThresholdsTo6(boundariesOrStops);
    const minVal = domainMin ?? (stops6[0] ?? 0) - Math.abs((stops6[0] ?? 0.1) * 0.25 || 0.1);
    const maxVal =
      domainMax ?? (stops6[5] ?? 1) + Math.abs((stops6[5] ?? 0.1) * 0.25 || 0.1);
    bounds8 = [minVal, ...stops6, maxVal];
  }

  const bins: LegendBin[] = [];
  for (let i = 0; i < 7; i++) {
    bins.push({
      index: i,
      min: bounds8[i] ?? i,
      max: bounds8[i + 1] ?? i + 1,
      color: palette[i] ?? palette[0],
    });
  }
  return bins;
}

const KNOWN_ORDINAL_ORDERS: Record<string, number> = {
  "A+": 1,
  A: 2,
  "B+": 3,
  B: 4,
  C: 5,
  D: 6,
};

/**
 * Encodes indicator rows (which may contain categorical/ordinal strings like CAPAG ratings)
 * into numeric values suitable for `map.setFeatureState`.
 */
export function encodeIndicatorRowsForMap(
  rows: ReadonlyArray<IndicatorMapRow>,
  valueType: ValueTypeCode,
): {
  numericRows: [number, number | null][];
  categories: string[];
} {
  if (valueType === "continuous") {
    const numericRows: [number, number | null][] = rows.map(([cdIbge, val]) => [
      cdIbge,
      typeof val === "number" && Number.isFinite(val) ? val : null,
    ]);
    return { numericRows, categories: [] };
  }

  const uniqueSet = new Set<string>();
  for (const [, val] of rows) {
    if (typeof val === "string" && val.trim().length > 0) {
      uniqueSet.add(val.trim());
    }
  }
  const categories = Array.from(uniqueSet).sort((a, b) => {
    const oa = KNOWN_ORDINAL_ORDERS[a];
    const ob = KNOWN_ORDINAL_ORDERS[b];
    if (oa !== undefined && ob !== undefined) {
      return oa - ob;
    }
    return a.localeCompare(b, "pt-BR");
  });

  const catIndex = new Map<string, number>();
  categories.forEach((cat, idx) => {
    catIndex.set(cat, idx);
  });

  const numericRows: [number, number | null][] = rows.map(([cdIbge, val]) => {
    if (typeof val === "number" && Number.isFinite(val)) {
      return [cdIbge, val];
    }
    if (typeof val === "string") {
      const idx = catIndex.get(val.trim());
      return [cdIbge, idx !== undefined ? idx : null];
    }
    return [cdIbge, null];
  });

  return { numericRows, categories };
}

/**
 * Partitions valid `(cd_ibge, value)` pairs into 10 deterministic deciles (1..10),
 * breaking ties by `cd_ibge` ascending (`docs/07-metodologia.md` §4.4).
 */
export function computeDecileMembership(
  rows: ReadonlyArray<readonly [number, number | string | null]>,
): Map<number, number> {
  const valid: [number, number][] = [];
  for (const [cdIbge, val] of rows) {
    if (typeof val === "number" && Number.isFinite(val)) {
      valid.push([cdIbge, val]);
    }
  }

  valid.sort((a, b) => {
    if (a[1] !== b[1]) {
      return a[1] - b[1];
    }
    return a[0] - b[0];
  });

  const n = valid.length;
  const result = new Map<number, number>();
  if (n === 0) {
    return result;
  }

  const baseSize = Math.floor(n / 10);
  const remainder = n % 10;
  let offset = 0;

  for (let d = 1; d <= 10; d++) {
    const chunkSize = baseSize + (d <= remainder ? 1 : 0);
    for (let i = 0; i < chunkSize && offset < n; i++, offset++) {
      const item = valid[offset];
      if (item) {
        result.set(item[0], d);
      }
    }
  }

  return result;
}

export interface FeatureStateTarget {
  setFeatureState(
    feature: { source: string; sourceLayer?: string; id: number },
    state: Record<string, unknown>,
  ): void;
}

/**
 * Applies municipality metric values in a single batch via `setFeatureState` (`docs/09-frontend.md` §3.2).
 */
export function applyMetricToMap(
  map: FeatureStateTarget,
  rows: ReadonlyArray<readonly [number, number | null]>,
  activeSet?: ReadonlySet<number> | null,
): void {
  const hasActiveFilter = Boolean(activeSet && activeSet.size > 0);
  for (let i = 0; i < rows.length; i++) {
    const row = rows[i];
    if (!row) {
      continue;
    }
    const [cdIbge, metric] = row;
    map.setFeatureState(
      { source: "territorio-mun", sourceLayer: "municipalities", id: cdIbge },
      {
        metric,
        inActiveDecile: hasActiveFilter ? Boolean(activeSet?.has(cdIbge)) : false,
      },
    );
  }
}

