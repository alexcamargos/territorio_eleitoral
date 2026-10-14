/**
 * Bidirectional synchronization between Preact signals and `URLSearchParams` (`docs/09-frontend.md` §2).
 */

import { effect } from "@preact/signals";
import type {
  BlocCode,
  MapLayerMode,
  OfficeCode,
  StoryStep,
} from "../types/api";
import {
  blocSignal,
  geoLevelSignal,
  indicatorSignal,
  mapLayerModeSignal,
  officeSignal,
  roundSignal,
  selectedIbgeSignal,
  storyStepSignal,
  ufFilterSignal,
  yearSignal,
} from "./store";

const VALID_OFFICES = new Set<OfficeCode>([
  "president",
  "governor",
  "senator",
  "federal_deputy",
  "state_deputy",
  "district_deputy",
  "state_or_district_deputy",
]);

const VALID_BLOCS = new Set<BlocCode>(["left", "center", "right"]);

const VALID_LAYERS = new Set<MapLayerMode>([
  "electoral_balance",
  "electoral_bloc",
  "indicator",
]);

/**
 * Serializes current exploration signals into a `URLSearchParams` instance.
 */
export function serializeStoreToSearchParams(): URLSearchParams {
  const params = new URLSearchParams();
  params.set("year", String(yearSignal.value));
  params.set("office", officeSignal.value);
  params.set("round", String(roundSignal.value));
  params.set("bloc", blocSignal.value);
  params.set("layer", mapLayerModeSignal.value);
  params.set("step", String(storyStepSignal.value));
  params.set("level", geoLevelSignal.value === "state" ? "macro" : "micro");

  if (indicatorSignal.value) {
    params.set("indicator", indicatorSignal.value);
  }
  if (ufFilterSignal.value) {
    params.set("uf", ufFilterSignal.value);
  }
  if (selectedIbgeSignal.value !== null) {
    params.set("mun", String(selectedIbgeSignal.value));
  }
  return params;
}

/**
 * Parses a URL query string into the global exploration signals, validating domains and invariants.
 */
export function parseSearchParamsToStore(search: string): void {
  const params = new URLSearchParams(search);

  const rawYear = Number(params.get("year"));
  if (Number.isInteger(rawYear) && rawYear >= 2018 && rawYear <= 2030) {
    yearSignal.value = rawYear;
  }

  const rawOffice = params.get("office")?.trim().toLowerCase() as
    | OfficeCode
    | undefined;
  if (rawOffice && VALID_OFFICES.has(rawOffice)) {
    officeSignal.value = rawOffice;
  }

  const rawRound = Number(params.get("round"));
  const canR2 =
    officeSignal.value === "president" || officeSignal.value === "governor";
  if (rawRound === 2 && canR2) {
    roundSignal.value = 2;
  } else {
    roundSignal.value = 1;
  }

  const rawBloc = params.get("bloc")?.trim().toLowerCase() as
    | BlocCode
    | undefined;
  if (rawBloc && VALID_BLOCS.has(rawBloc)) {
    blocSignal.value = rawBloc;
  }

  const rawIndicator = params.get("indicator")?.trim() || null;
  indicatorSignal.value = rawIndicator;

  const rawUf = params.get("uf")?.trim().toUpperCase() || null;
  ufFilterSignal.value =
    rawUf && /^[A-Z]{2}$/.test(rawUf) ? rawUf : null;

  const rawMun = Number(params.get("mun"));
  selectedIbgeSignal.value =
    Number.isInteger(rawMun) && rawMun >= 1100000 && rawMun <= 5399999
      ? rawMun
      : null;

  const rawStep = Number(params.get("step"));
  let step: StoryStep =
    rawStep === 1 || rawStep === 2 || rawStep === 3 || rawStep === 4
      ? rawStep
      : 1;

  if (rawIndicator && step < 3) {
    step = 3;
  } else if (!rawIndicator && step >= 3) {
    step = 1;
  }
  storyStepSignal.value = step;

  const rawLayer = params.get("layer")?.trim() as MapLayerMode | undefined;
  if (rawLayer && VALID_LAYERS.has(rawLayer)) {
    if (rawLayer === "indicator" && !rawIndicator) {
      mapLayerModeSignal.value = "electoral_balance";
    } else {
      mapLayerModeSignal.value = rawLayer;
    }
  } else {
    mapLayerModeSignal.value = rawIndicator ? "indicator" : "electoral_balance";
  }

  const rawLevel = params.get("level")?.trim().toLowerCase();
  if (rawLevel === "micro" || rawLevel === "municipality" || (selectedIbgeSignal.value !== null && rawLevel !== "macro")) {
    geoLevelSignal.value = "municipality";
  } else if (rawLevel === "macro" || rawLevel === "state") {
    geoLevelSignal.value = "state";
  } else {
    geoLevelSignal.value = "state";
  }
}

/**
 * Initializes two-way synchronization between `window.location.search` and signals.
 */
export function initUrlSynchronization(): () => void {
  if (typeof window === "undefined") {
    return () => {};
  }

  parseSearchParamsToStore(window.location.search);

  let isUpdatingFromPopState = false;

  const disposeEffect = effect(() => {
    const params = serializeStoreToSearchParams();
    const nextSearch = `?${params.toString()}`;
    if (!isUpdatingFromPopState && window.location.search !== nextSearch) {
      window.history.replaceState(null, "", nextSearch);
    }
  });

  const handlePopState = (): void => {
    isUpdatingFromPopState = true;
    try {
      parseSearchParamsToStore(window.location.search);
    } finally {
      isUpdatingFromPopState = false;
    }
  };

  window.addEventListener("popstate", handlePopState);
  return () => {
    disposeEffect();
    window.removeEventListener("popstate", handlePopState);
  };
}
