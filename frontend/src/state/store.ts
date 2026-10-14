/**
 * Reactive global exploration state built with `@preact/signals` (`docs/09-frontend.md` §2).
 */

import { computed, signal } from "@preact/signals";
import type {
  AnalysisResponse,
  BlocCode,
  ElectionMapResponse,
  GeoLevel,
  IndicatorMapResponse,
  IndicatorMeta,
  MapLayerMode,
  MetaResponse,
  OfficeCode,
  StoryStep,
  StoryTrack,
  ThemeMode,
} from "../types/api";

export const geoLevelSignal = signal<GeoLevel>("state");
export const yearSignal = signal<number>(2026);
export const officeSignal = signal<OfficeCode>("president");
export const roundSignal = signal<1 | 2>(1);
export const blocSignal = signal<BlocCode>("right");
export const indicatorSignal = signal<string | null>(null);
export const ufFilterSignal = signal<string | null>(null);
export const storyStepSignal = signal<StoryStep>(1);
export const mapLayerModeSignal = signal<MapLayerMode>("electoral_balance");

export const hoveredIbgeSignal = signal<number | null>(null);
export const selectedIbgeSignal = signal<number | null>(null);
export const hoveredUfSignal = signal<string | null>(null);
export const selectedUfSignal = signal<string | null>(null);
export const activeDecileSignal = signal<number | null>(null);
export const activeLegendBinSignal = signal<number | null>(null);
export const cursorPositionSignal = signal<{ x: number; y: number }>({
  x: 0,
  y: 0,
});
export const mapBoundsTargetSignal = signal<
  [number, number, number, number] | null
>(null);

export const themeSignal = signal<ThemeMode>("light");
export const isMethodologyOpenSignal = signal<boolean>(false);
export const viewModeTableSignal = signal<boolean>(false);

// Storytelling improvements signals: Swipe / Cortina, Trilhas Editoriais e Ancoragem
export const isSwipeModeSignal = signal<boolean>(false);
export const swipePositionSignal = signal<number>(50);
export const activeStoryTrackSignal = signal<string | null>(null);
export const anchoredMunicipalitySignal = signal<number | null>(null);

// Loaded API datasets (Municipal & UF level)
export const metaDataSignal = signal<MetaResponse | null>(null);
export const electionMapDataSignal = signal<ElectionMapResponse | null>(null);
export const electionUfMapDataSignal = signal<ElectionMapResponse | null>(null);
export const indicatorMapDataSignal = signal<IndicatorMapResponse | null>(null);
export const indicatorUfMapDataSignal = signal<IndicatorMapResponse | null>(null);
export const analysisDataSignal = signal<AnalysisResponse | null>(null);
export const analysisUfDataSignal = signal<AnalysisResponse | null>(null);

// Loading & Error signals
export const isLoadingMapSignal = signal<boolean>(false);
export const isLoadingAnalysisSignal = signal<boolean>(false);
export const apiErrorSignal = signal<string | null>(null);

// Fast lookup dictionary populated from MVT tiles and search results
export interface MunicipalityBasicInfo {
  cd_ibge: number;
  name: string;
  uf: string;
  region: string;
}

export const municipalityDirectorySignal = signal<
  ReadonlyMap<number, MunicipalityBasicInfo>
>(new Map());

export function registerMunicipalitiesInDirectory(
  items: readonly MunicipalityBasicInfo[],
): void {
  if (items.length === 0) {
    return;
  }
  const current = municipalityDirectorySignal.value;
  let changed = false;
  for (const item of items) {
    if (!current.has(item.cd_ibge)) {
      changed = true;
      break;
    }
  }
  if (!changed) {
    return;
  }
  const next = new Map(current);
  for (const item of items) {
    next.set(item.cd_ibge, item);
  }
  municipalityDirectorySignal.value = next;
}

export const canSelectRound2 = computed<boolean>(
  () => officeSignal.value === "president" || officeSignal.value === "governor",
);

export const activeIndicatorMeta = computed<IndicatorMeta | null>(() => {
  const code = indicatorSignal.value;
  const meta = metaDataSignal.value;
  if (!code || !meta) {
    return null;
  }
  return meta.indicators.find((item) => item.code === code) ?? null;
});

/**
 * Lookup map from `cd_ibge` to electoral row `[left_share, center_share, right_share, lr_balance, leading_bloc, valid_votes]`
 */
export const electionByIbgeMap = computed<
  ReadonlyMap<
    number,
    {
      leftShare: number;
      centerShare: number;
      rightShare: number;
      lrBalance: number;
      leadingBloc: BlocCode;
      validVotes: number;
    }
  >
>(() => {
  const data = electionMapDataSignal.value;
  const map = new Map<
    number,
    {
      leftShare: number;
      centerShare: number;
      rightShare: number;
      lrBalance: number;
      leadingBloc: BlocCode;
      validVotes: number;
    }
  >();
  if (!data) {
    return map;
  }
  for (const row of data.rows) {
    if (typeof row[0] === "number") {
      map.set(row[0], {
        leftShare: Number(row[1]),
        centerShare: Number(row[2]),
        rightShare: Number(row[3]),
        lrBalance: Number(row[4]),
        leadingBloc: row[5] as BlocCode,
        validVotes: Number(row[6]),
      });
    }
  }
  return map;
});

export interface UfElectionInfo {
  uf: string;
  ufCode: number;
  name: string;
  leftShare: number;
  centerShare: number;
  rightShare: number;
  lrBalance: number;
  leadingBloc: BlocCode;
  validVotes: number;
  turnoutPct: number;
  leadingShare: number;
}

/**
 * Lookup map from `uf` to electoral data row
 */
export const electionByUfMap = computed<ReadonlyMap<string, UfElectionInfo>>(() => {
  const data = electionUfMapDataSignal.value;
  const map = new Map<string, UfElectionInfo>();
  if (!data) {
    return map;
  }
  for (const r of data.rows) {
    if (typeof r[0] === "string") {
      map.set(r[0], {
        uf: r[0],
        ufCode: Number(r[1]),
        name: String(r[2]),
        leftShare: Number(r[3]),
        centerShare: Number(r[4]),
        rightShare: Number(r[5]),
        lrBalance: Number(r[6]),
        leadingBloc: r[7] as BlocCode,
        validVotes: Number(r[8]),
        turnoutPct: Number(r[9]),
        leadingShare: Number(r[10]),
      });
    }
  }
  return map;
});

/**
 * Lookup map from `uf` to indicator value (`number | null`).
 */
export const indicatorValueByUfMap = computed<
  ReadonlyMap<string, number | null>
>(() => {
  const data = indicatorUfMapDataSignal.value;
  const map = new Map<string, number | null>();
  if (!data) {
    return map;
  }
  for (const r of data.rows) {
    if (typeof r[0] === "string") {
      map.set(r[0], typeof r[3] === "number" ? r[3] : null);
    }
  }
  return map;
});

/**
 * Lookup map from `cd_ibge` to indicator value (`number | string | null`).
 */
export const indicatorValueByIbgeMap = computed<
  ReadonlyMap<number, number | string | null>
>(() => {
  const data = indicatorMapDataSignal.value;
  const map = new Map<number, number | string | null>();
  if (!data) {
    return map;
  }
  for (const row of data.rows) {
    if (typeof row[0] === "number") {
      map.set(row[0], row[1] as number | string | null);
    }
  }
  return map;
});

/**
 * Action: Toggles between Macro (state) and Micro (municipality) analysis mode.
 */
export function setGeoLevel(level: GeoLevel): void {
  geoLevelSignal.value = level;
  if (level === "state") {
    selectedIbgeSignal.value = null;
    hoveredIbgeSignal.value = null;
  }
}

/**
 * Action: Drills down into a specific state, switching to Micro mode and zooming into its municipalities.
 */
export function drillDownToState(uf: string): void {
  ufFilterSignal.value = uf;
  geoLevelSignal.value = "municipality";
  const meta = metaDataSignal.value;
  const found = meta?.ufs.find((u) => u.uf === uf);
  if (found?.bbox) {
    mapBoundsTargetSignal.value = found.bbox;
  }
}

/**
 * Action: Selects an office and automatically resets `roundSignal` to 1 if round 2 is unsupported.
 */
export function selectOffice(office: OfficeCode): void {
  officeSignal.value = office;
  if (office !== "president" && office !== "governor" && roundSignal.value === 2) {
    roundSignal.value = 1;
  }
}

/**
 * Action: Selects an indicator and transitions storytelling state to Step 3 (A Revelação).
 */
export function selectIndicator(code: string | null): void {
  indicatorSignal.value = code;
  activeDecileSignal.value = null;
  activeLegendBinSignal.value = null;
  if (code !== null) {
    if (storyStepSignal.value < 3) {
      storyStepSignal.value = 3;
    }
    mapLayerModeSignal.value = "indicator";
  } else {
    storyStepSignal.value = 1;
    mapLayerModeSignal.value = "electoral_balance";
  }
}

/**
 * Action: Navigates directly to one of the 4 storytelling steps (`docs/09-frontend.md` §2).
 */
export function navigateToStoryStep(step: StoryStep): void {
  storyStepSignal.value = step;
  if (step === 1) {
    mapLayerModeSignal.value = "electoral_balance";
    activeDecileSignal.value = null;
  } else if (step >= 3 && indicatorSignal.value !== null) {
    mapLayerModeSignal.value = "indicator";
  }
}

/**
 * Action: Applies an editorial story track preset to global state.
 */
export function applyStoryTrack(track: StoryTrack): void {
  activeStoryTrackSignal.value = track.id;
  officeSignal.value = track.preset.office;
  roundSignal.value = track.preset.round;
  blocSignal.value = track.preset.bloc;
  ufFilterSignal.value = track.preset.uf;
  indicatorSignal.value = track.preset.indicator;
  activeDecileSignal.value = null;
  activeLegendBinSignal.value = null;
  storyStepSignal.value = 3;
  mapLayerModeSignal.value = "indicator";
}

/**
 * Resets all exploration signals to initial defaults (used in tests and reset button).
 */
export function resetStoreToDefaults(): void {
  geoLevelSignal.value = "state";
  yearSignal.value = 2026;
  officeSignal.value = "president";
  roundSignal.value = 1;
  blocSignal.value = "right";
  indicatorSignal.value = null;
  ufFilterSignal.value = null;
  storyStepSignal.value = 1;
  mapLayerModeSignal.value = "electoral_balance";
  hoveredIbgeSignal.value = null;
  selectedIbgeSignal.value = null;
  hoveredUfSignal.value = null;
  selectedUfSignal.value = null;
  activeDecileSignal.value = null;
  activeLegendBinSignal.value = null;
  viewModeTableSignal.value = false;
  isSwipeModeSignal.value = false;
  swipePositionSignal.value = 50;
  activeStoryTrackSignal.value = null;
  anchoredMunicipalitySignal.value = null;
}
