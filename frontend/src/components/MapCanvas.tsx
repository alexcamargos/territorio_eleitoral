import { useEffect, useRef, useState } from "preact/hooks";
import maplibregl, {
  type ExpressionSpecification,
  type StyleSpecification,
} from "maplibre-gl";
import { BLOC_LABELS_PT } from "../lib/format";
import {
  applyMetricToMap,
  buildLegendBins,
  buildMapLibreColorExpression,
  computeDecileMembership,
  encodeIndicatorRowsForMap,
  getColorForMetricValue,
  getElectoralPalette,
  getIndicatorPalette,
  getThemeMapColors,
} from "../lib/scales";
import {
  activeDecileSignal,
  activeIndicatorMeta,
  activeLegendBinSignal,
  blocSignal,
  cursorPositionSignal,
  electionMapDataSignal,
  electionUfMapDataSignal,
  geoLevelSignal,
  hoveredIbgeSignal,
  hoveredUfSignal,
  indicatorMapDataSignal,
  indicatorUfMapDataSignal,
  indicatorSignal,
  isSwipeModeSignal,
  mapBoundsTargetSignal,
  mapLayerModeSignal,
  metaDataSignal,
  registerMunicipalitiesInDirectory,
  selectedIbgeSignal,
  selectedUfSignal,
  themeSignal,
  type MunicipalityBasicInfo,
} from "../state/store";
import { MapLegend } from "./MapLegend";
import { MapSwipe } from "./MapSwipe";
import { StateFocusCard } from "./StateFocusCard";
import { StateLabelsOverlay } from "./StateLabelsOverlay";
import type { ElectionMapRow, IndicatorMapRow } from "../types/api";

export { applyMetricToMap };

const UF_CODE_MAP: Record<string, number> = {
  RO: 11,
  AC: 12,
  AM: 13,
  RR: 14,
  PA: 15,
  AP: 16,
  TO: 17,
  MA: 21,
  PI: 22,
  CE: 23,
  RN: 24,
  PB: 25,
  PE: 26,
  AL: 27,
  SE: 28,
  BA: 29,
  MG: 31,
  ES: 32,
  RJ: 33,
  SP: 35,
  PR: 41,
  SC: 42,
  RS: 43,
  MS: 50,
  MT: 51,
  GO: 52,
  DF: 53,
};

export function MapCanvas() {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const [mapInstance, setMapInstance] = useState<maplibregl.Map | null>(null);
  const isLoadedRef = useRef<boolean>(false);
  const prevHoveredRef = useRef<number | null>(null);
  const prevSelectedRef = useRef<number | null>(null);
  const prevHoveredUfRef = useRef<string | null>(null);
  const prevSelectedUfRef = useRef<string | null>(null);

  const hasIndicator = indicatorSignal.value !== null;
  const layerMode = mapLayerModeSignal.value;

  // Keyboard shortcut `M`: toggle between Indicator and Electoral Vote layer
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent): void => {
      const target = e.target as HTMLElement | null;
      if (
        target &&
        (target.tagName === "INPUT" ||
          target.tagName === "SELECT" ||
          target.tagName === "TEXTAREA" ||
          target.isContentEditable)
      ) {
        return;
      }
      if (e.key.toLowerCase() === "m" && indicatorSignal.value !== null) {
        e.preventDefault();
        mapLayerModeSignal.value =
          mapLayerModeSignal.value === "indicator"
            ? "electoral_bloc"
            : "indicator";
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  // Initialize MapLibre GL JS with token-free local StyleSpecification
  useEffect(() => {
    const container = containerRef.current;
    if (!container || mapRef.current) {
      return;
    }

    const themeColors = getThemeMapColors(themeSignal.value);
    const dv = metaDataSignal.value?.dataset_version ?? 1;
    const origin = window.location.origin;

    const style: StyleSpecification = {
      version: 8,
      sources: {
        "territorio-mun": {
          type: "vector",
          tiles: [`${origin}/tiles/municipalities/{z}/{x}/{y}.pbf?v=${dv}`],
          minzoom: 0,
          maxzoom: 12,
        },
      },
      layers: [
        {
          id: "background",
          type: "background",
          paint: {
            "background-color": themeColors.background,
          },
        },
        {
          id: "uf-fill",
          type: "fill",
          source: "territorio-mun",
          "source-layer": "ufs",
          layout: {
            visibility: geoLevelSignal.value === "state" ? "visible" : "none",
          },
          paint: {
            "fill-color": themeColors.noData,
            "fill-outline-color": themeColors.ufStroke,
            "fill-opacity": 0.92,
          },
        },
        {
          id: "mun-fill",
          type: "fill",
          source: "territorio-mun",
          "source-layer": "municipalities",
          layout: {
            visibility: geoLevelSignal.value === "municipality" ? "visible" : "none",
          },
          paint: {
            "fill-color": themeColors.noData,
            "fill-outline-color": themeColors.munStroke,
            "fill-opacity": [
              "case",
              ["boolean", ["feature-state", "inActiveDecile"], false],
              0.98,
              0.88,
            ],
          },
        },
        {
          id: "mun-border",
          type: "line",
          source: "territorio-mun",
          "source-layer": "municipalities",
          minzoom: 5,
          layout: {
            visibility: geoLevelSignal.value === "municipality" ? "visible" : "none",
          },
          paint: {
            "line-color": themeColors.munStroke,
            "line-width": [
              "interpolate",
              ["linear"],
              ["zoom"],
              5,
              0.3,
              8,
              0.6,
              12,
              1.1,
            ],
          },
        },
        {
          id: "uf-border",
          type: "line",
          source: "territorio-mun",
          "source-layer": "ufs",
          paint: {
            "line-color": themeColors.ufStroke,
            "line-width": [
              "interpolate",
              ["linear"],
              ["zoom"],
              3,
              0.9,
              8,
              1.5,
              12,
              2.2,
            ],
          },
        },
        {
          id: "uf-highlight",
          type: "line",
          source: "territorio-mun",
          "source-layer": "ufs",
          layout: {
            visibility: geoLevelSignal.value === "state" ? "visible" : "none",
          },
          paint: {
            "line-color": themeColors.hoverStroke,
            "line-width": [
              "case",
              ["boolean", ["feature-state", "selected"], false],
              3.0,
              ["boolean", ["feature-state", "hovered"], false],
              2.2,
              0,
            ],
          },
        },
        {
          id: "mun-highlight",
          type: "line",
          source: "territorio-mun",
          "source-layer": "municipalities",
          layout: {
            visibility: geoLevelSignal.value === "municipality" ? "visible" : "none",
          },
          paint: {
            "line-color": themeColors.hoverStroke,
            "line-width": [
              "case",
              ["boolean", ["feature-state", "selected"], false],
              2.4,
              ["boolean", ["feature-state", "hovered"], false],
              2.0,
              ["boolean", ["feature-state", "inActiveDecile"], false],
              1.5,
              0,
            ],
          },
        },
      ],
    };

    const map = new maplibregl.Map({
      container,
      style,
      center: [-52.0, -14.5],
      zoom: 3.6,
      minZoom: 3,
      maxZoom: 14,
      attributionControl: false,
    });

    map.addControl(
      new maplibregl.NavigationControl({ showCompass: false }),
      "bottom-right",
    );

    map.on("load", () => {
      isLoadedRef.current = true;
      setMapInstance(map);
      syncMapPaintAndFeatureStates();
    });

    // Index municipality names & UFs from loaded vector tiles so ScatterPlot hover has full metadata
    map.on("sourcedata", (e) => {
      if (e.sourceId === "territorio-mun" && e.isSourceLoaded) {
        if (geoLevelSignal.value === "municipality") {
          const features = map.querySourceFeatures("territorio-mun", {
            sourceLayer: "municipalities",
          });
          const items: MunicipalityBasicInfo[] = [];
          for (const f of features) {
            const props = f.properties as Record<string, unknown> | undefined;
            const cd = Number(props?.["cd_ibge"] ?? f.id);
            const name = String(props?.["name"] ?? "");
            const uf = String(props?.["uf"] ?? "");
            const region = String(props?.["region"] ?? "");
            if (Number.isInteger(cd) && name) {
              items.push({ cd_ibge: cd, name, uf, region });
            }
          }
          registerMunicipalitiesInDirectory(items);
        }
        syncMapPaintAndFeatureStates();
      }
    });

    map.on("mousemove", "uf-fill", (e) => {
      if (geoLevelSignal.value !== "state") {
        return;
      }
      map.getCanvas().style.cursor = "pointer";
      cursorPositionSignal.value = {
        x: e.originalEvent.clientX,
        y: e.originalEvent.clientY,
      };
      const feature = e.features?.[0];
      if (!feature) {
        return;
      }
      const props = feature.properties as Record<string, unknown> | undefined;
      const uf = String(props?.["uf"] ?? "");
      if (uf) {
        hoveredUfSignal.value = uf;
      }
    });

    map.on("mouseleave", "uf-fill", () => {
      if (geoLevelSignal.value !== "state") {
        return;
      }
      map.getCanvas().style.cursor = "";
      hoveredUfSignal.value = null;
    });

    map.on("click", "uf-fill", (e) => {
      if (geoLevelSignal.value !== "state") {
        return;
      }
      const feature = e.features?.[0];
      if (!feature) {
        return;
      }
      const props = feature.properties as Record<string, unknown> | undefined;
      const uf = String(props?.["uf"] ?? "");
      if (uf) {
        selectedUfSignal.value = uf;
      }
    });

    map.on("mousemove", "mun-fill", (e) => {
      if (geoLevelSignal.value !== "municipality") {
        return;
      }
      map.getCanvas().style.cursor = "pointer";
      cursorPositionSignal.value = {
        x: e.originalEvent.clientX,
        y: e.originalEvent.clientY,
      };
      const feature = e.features?.[0];
      if (!feature) {
        return;
      }
      const props = feature.properties as Record<string, unknown> | undefined;
      const cdIbge = Number(props?.["cd_ibge"] ?? feature.id);
      if (Number.isInteger(cdIbge)) {
        const name = String(props?.["name"] ?? "");
        const uf = String(props?.["uf"] ?? "");
        const region = String(props?.["region"] ?? "");
        if (name) {
          registerMunicipalitiesInDirectory([
            { cd_ibge: cdIbge, name, uf, region },
          ]);
        }
        hoveredIbgeSignal.value = cdIbge;
      }
    });

    map.on("mouseleave", "mun-fill", () => {
      if (geoLevelSignal.value !== "municipality") {
        return;
      }
      map.getCanvas().style.cursor = "";
      hoveredIbgeSignal.value = null;
    });

    map.on("click", "mun-fill", (e) => {
      if (geoLevelSignal.value !== "municipality") {
        return;
      }
      const feature = e.features?.[0];
      if (!feature) {
        return;
      }
      const props = feature.properties as Record<string, unknown> | undefined;
      const cdIbge = Number(props?.["cd_ibge"] ?? feature.id);
      if (Number.isInteger(cdIbge)) {
        selectedIbgeSignal.value = cdIbge;
      }
    });

    mapRef.current = map;
    (window as unknown as { __map?: maplibregl.Map }).__map = map;
    return () => {
      isLoadedRef.current = false;
      delete (window as unknown as { __map?: maplibregl.Map }).__map;
      setMapInstance(null);
      map.remove();
      mapRef.current = null;
    };
  }, []);

  // Re-paint choropleth via `setFeatureState` whenever data, mode, bloc, decile, or theme changes
  const syncMapPaintAndFeatureStates = (): void => {
    const map = mapRef.current;
    if (!map || !isLoadedRef.current) {
      return;
    }

    const isMacro = geoLevelSignal.value === "state";
    const themeColors = getThemeMapColors(themeSignal.value);

    const safeSetPaint = (id: string, prop: string, value: unknown): void => {
      if (map.getLayer(id)) {
        map.setPaintProperty(id, prop, value);
      }
    };

    const safeSetLayout = (id: string, prop: string, value: unknown): void => {
      if (map.getLayer(id)) {
        map.setLayoutProperty(id, prop, value);
      }
    };

    safeSetPaint("background", "background-color", themeColors.background);
    safeSetPaint("mun-fill", "fill-outline-color", themeColors.munStroke);
    safeSetPaint("mun-border", "line-color", themeColors.munStroke);
    safeSetPaint("uf-border", "line-color", themeColors.ufStroke);
    safeSetPaint("mun-highlight", "line-color", themeColors.hoverStroke);
    safeSetPaint("uf-highlight", "line-color", themeColors.hoverStroke);

    safeSetLayout("uf-fill", "visibility", isMacro ? "visible" : "none");
    safeSetLayout("uf-highlight", "visibility", isMacro ? "visible" : "none");
    safeSetLayout("mun-fill", "visibility", isMacro ? "none" : "visible");
    safeSetLayout("mun-border", "visibility", isMacro ? "none" : "visible");
    safeSetLayout("mun-highlight", "visibility", isMacro ? "none" : "visible");

    const mode = mapLayerModeSignal.value;
    const bloc = blocSignal.value;
    const activeDecile = activeDecileSignal.value;
    const activeBin = activeLegendBinSignal.value;
    const indMeta = activeIndicatorMeta.value;

    if (isMacro) {
      const ufIndData = indicatorUfMapDataSignal.value;
      const ufElecData = electionUfMapDataSignal.value;

      if (mode === "indicator" && ufIndData && indMeta) {
        const palette = getIndicatorPalette(indMeta.theme);
        const quantiles = ufIndData.summary.quantiles_7;
        const ufColorMatch: unknown[] = ["match", ["get", "uf"]];

        for (const row of ufIndData.rows) {
          if (typeof row[0] === "string") {
            const ufSigla = String(row[0]);
            const ufCode = Number(row[1]) || UF_CODE_MAP[ufSigla] || 0;
            const val = typeof row[3] === "number" ? row[3] : null;
            const color = getColorForMetricValue(
              val,
              quantiles,
              palette,
              themeColors.noData,
            );
            ufColorMatch.push(ufSigla, color);
            map.setFeatureState(
              { source: "territorio-mun", sourceLayer: "ufs", id: ufCode },
              { metric: val, hasMetric: val !== null },
            );
          }
        }
        ufColorMatch.push(themeColors.noData);
        safeSetPaint(
          "uf-fill",
          "fill-color",
          ufColorMatch as ExpressionSpecification,
        );
        return;
      }

      if (ufElecData) {
        const effectiveMode =
          mode === "indicator" ? "electoral_balance" : mode;
        const palette = getElectoralPalette(effectiveMode, bloc);
        const thresholds =
          effectiveMode === "electoral_bloc"
            ? bloc === "left"
              ? ufElecData.quantiles.left_share
              : bloc === "center"
                ? (ufElecData.quantiles.center_share ?? ufElecData.quantiles.right_share)
                : ufElecData.quantiles.right_share
            : ufElecData.quantiles.lr_balance;

        const ufColorMatch: unknown[] = ["match", ["get", "uf"]];

        for (const r of ufElecData.rows) {
          if (typeof r[0] === "string") {
            const ufSigla = String(r[0]);
            const ufCode = Number(r[1]) || UF_CODE_MAP[ufSigla] || 0;
            const val =
              effectiveMode === "electoral_bloc"
                ? bloc === "left"
                  ? Number(r[3])
                  : bloc === "center"
                    ? Number(r[4])
                    : Number(r[5])
                : Number(r[6]);
            const color = getColorForMetricValue(
              val,
              thresholds,
              palette,
              themeColors.noData,
            );
            ufColorMatch.push(ufSigla, color);
            map.setFeatureState(
              { source: "territorio-mun", sourceLayer: "ufs", id: ufCode },
              { metric: val, hasMetric: true },
            );
          }
        }
        ufColorMatch.push(themeColors.noData);
        safeSetPaint(
          "uf-fill",
          "fill-color",
          ufColorMatch as ExpressionSpecification,
        );
      }
      return;
    }

    const electionData = electionMapDataSignal.value;
    const indicatorData = indicatorMapDataSignal.value;

    const munIndicatorRows: IndicatorMapRow[] = indicatorData
      ? indicatorData.rows.filter(
          (r): r is IndicatorMapRow => typeof r[0] === "number",
        )
      : [];

    const munElectionRows: ElectionMapRow[] = electionData
      ? electionData.rows.filter(
          (r): r is ElectionMapRow => typeof r[0] === "number",
        )
      : [];

    if (mode === "indicator" && indicatorData && indMeta) {
      const palette = getIndicatorPalette(indMeta.theme);
      const encoded = encodeIndicatorRowsForMap(
        munIndicatorRows,
        indMeta.value_type,
      );
      const quantiles = indicatorData.summary.quantiles_7;
      const colorExpr = buildMapLibreColorExpression(
        quantiles,
        palette,
        themeColors.noData,
      );
      map.setPaintProperty(
        "mun-fill",
        "fill-color",
        colorExpr as ExpressionSpecification,
      );

      let highlightedSet: Set<number> | null = null;
      if (activeDecile !== null) {
        const decileMap = computeDecileMembership(encoded.numericRows);
        highlightedSet = new Set<number>();
        for (const [cd, dec] of decileMap.entries()) {
          if (dec === activeDecile) {
            highlightedSet.add(cd);
          }
        }
      } else if (activeBin !== null) {
        const bins = buildLegendBins(quantiles, palette);
        const targetBin = bins[activeBin];
        if (targetBin) {
          highlightedSet = new Set<number>();
          for (const [cd, val] of encoded.numericRows) {
            if (
              val !== null &&
              val >= targetBin.min &&
              (activeBin === 6 ? val <= targetBin.max : val < targetBin.max)
            ) {
              highlightedSet.add(cd);
            }
          }
        }
      }

      applyMetricToMap(map, encoded.numericRows, highlightedSet);
      return;
    }

    if (electionData) {
      const effectiveMode =
        mode === "indicator" ? "electoral_balance" : mode;
      const palette = getElectoralPalette(effectiveMode, bloc);
      const thresholds =
        effectiveMode === "electoral_bloc"
          ? bloc === "left"
            ? electionData.quantiles.left_share
            : bloc === "center"
              ? (electionData.quantiles.center_share ?? electionData.quantiles.right_share)
              : electionData.quantiles.right_share
          : electionData.quantiles.lr_balance;

      const colorExpr = buildMapLibreColorExpression(
        thresholds,
        palette,
        themeColors.noData,
      );
      map.setPaintProperty(
        "mun-fill",
        "fill-color",
        colorExpr as ExpressionSpecification,
      );

      const metricRows: [number, number | null][] = munElectionRows.map(
        (r) => {
          if (effectiveMode === "electoral_bloc") {
            const share =
              bloc === "left" ? r[1] : bloc === "center" ? r[2] : r[3];
            return [r[0], share];
          }
          return [r[0], r[4]];
        },
      );

      let highlightedSet: Set<number> | null = null;
      if (activeDecile !== null && munIndicatorRows.length > 0) {
        const decileMap = computeDecileMembership(munIndicatorRows);
        highlightedSet = new Set<number>();
        for (const [cd, dec] of decileMap.entries()) {
          if (dec === activeDecile) {
            highlightedSet.add(cd);
          }
        }
      } else if (activeBin !== null) {
        const bins = buildLegendBins(
          thresholds,
          palette,
          effectiveMode === "electoral_bloc" ? 0 : -1,
          1,
        );
        const targetBin = bins[activeBin];
        if (targetBin) {
          highlightedSet = new Set<number>();
          for (const [cd, val] of metricRows) {
            if (
              val !== null &&
              val >= targetBin.min &&
              (activeBin === 6 ? val <= targetBin.max : val < targetBin.max)
            ) {
              highlightedSet.add(cd);
            }
          }
        }
      }

      applyMetricToMap(map, metricRows, highlightedSet);
    }
  };

  useEffect(() => {
    syncMapPaintAndFeatureStates();
  }, [
    geoLevelSignal.value,
    electionMapDataSignal.value,
    electionUfMapDataSignal.value,
    indicatorMapDataSignal.value,
    indicatorUfMapDataSignal.value,
    mapLayerModeSignal.value,
    blocSignal.value,
    activeDecileSignal.value,
    activeLegendBinSignal.value,
    themeSignal.value,
  ]);

  // Synchronize hoveredUfSignal with MapLibre ufs feature-state
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !isLoadedRef.current) {
      return;
    }
    const prev = prevHoveredUfRef.current;
    const next = hoveredUfSignal.value;
    if (prev && prev !== next && UF_CODE_MAP[prev]) {
      map.setFeatureState(
        { source: "territorio-mun", sourceLayer: "ufs", id: UF_CODE_MAP[prev] },
        { hovered: false },
      );
    }
    if (next && UF_CODE_MAP[next]) {
      map.setFeatureState(
        { source: "territorio-mun", sourceLayer: "ufs", id: UF_CODE_MAP[next] },
        { hovered: true },
      );
    }
    prevHoveredUfRef.current = next;
  }, [hoveredUfSignal.value]);

  // Synchronize selectedUfSignal with MapLibre ufs feature-state
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !isLoadedRef.current) {
      return;
    }
    const prev = prevSelectedUfRef.current;
    const next = selectedUfSignal.value;
    if (prev && prev !== next && UF_CODE_MAP[prev]) {
      map.setFeatureState(
        { source: "territorio-mun", sourceLayer: "ufs", id: UF_CODE_MAP[prev] },
        { selected: false },
      );
    }
    if (next && UF_CODE_MAP[next]) {
      map.setFeatureState(
        { source: "territorio-mun", sourceLayer: "ufs", id: UF_CODE_MAP[next] },
        { selected: true },
      );
    }
    prevSelectedUfRef.current = next;
  }, [selectedUfSignal.value]);

  // Synchronize hoveredIbgeSignal (from Map or ScatterPlot) with MapLibre feature-state
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !isLoadedRef.current) {
      return;
    }
    const prev = prevHoveredRef.current;
    const next = hoveredIbgeSignal.value;
    if (prev !== null && prev !== next) {
      map.setFeatureState(
        { source: "territorio-mun", sourceLayer: "municipalities", id: prev },
        { hovered: false },
      );
    }
    if (next !== null) {
      map.setFeatureState(
        { source: "territorio-mun", sourceLayer: "municipalities", id: next },
        { hovered: true },
      );
    }
    prevHoveredRef.current = next;
  }, [hoveredIbgeSignal.value]);

  // Synchronize selectedIbgeSignal with MapLibre feature-state
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !isLoadedRef.current) {
      return;
    }
    const prev = prevSelectedRef.current;
    const next = selectedIbgeSignal.value;
    if (prev !== null && prev !== next) {
      map.setFeatureState(
        { source: "territorio-mun", sourceLayer: "municipalities", id: prev },
        { selected: false },
      );
    }
    if (next !== null) {
      map.setFeatureState(
        { source: "territorio-mun", sourceLayer: "municipalities", id: next },
        { selected: true },
      );
    }
    prevSelectedRef.current = next;
  }, [selectedIbgeSignal.value]);

  // Smooth `fitBounds` when UF filter or municipality search sets `mapBoundsTargetSignal`
  useEffect(() => {
    const map = mapRef.current;
    const bounds = mapBoundsTargetSignal.value;
    if (!map || !isLoadedRef.current || !bounds) {
      return;
    }
    const prefersReducedMotion = window.matchMedia(
      "(prefers-reduced-motion: reduce)",
    ).matches;
    map.fitBounds(
      [
        [bounds[0], bounds[1]],
        [bounds[2], bounds[3]],
      ],
      {
        padding: 36,
        duration: prefersReducedMotion ? 0 : 450,
      },
    );
  }, [mapBoundsTargetSignal.value]);

  const isMacro = geoLevelSignal.value === "state";

  return (
    <section
      class="map-stage"
      aria-label="Mapa coroplético eleitoral e socioeconômico"
    >
      <div ref={containerRef} class="maplibre-container" />

      {isMacro && <StateLabelsOverlay map={mapInstance} />}
      {isMacro && <StateFocusCard />}

      <div class="map-floating-controls">
        <div class="layer-pill" role="group" aria-label="Modo de pintura do mapa">
          <span class="layer-pill-label">Pintar mapa por:</span>
          {hasIndicator && (
            <button
              type="button"
              class={`segmented-btn ${layerMode === "indicator" ? "is-active" : ""}`}
              aria-pressed={layerMode === "indicator"}
              title="Pintar pelo indicador selecionado (Atalho: tecla M)"
              onClick={() => {
                mapLayerModeSignal.value = "indicator";
              }}
            >
              Indicador
            </button>
          )}
          <button
            type="button"
            class={`segmented-btn ${layerMode === "electoral_balance" ? "is-active" : ""}`}
            aria-pressed={layerMode === "electoral_balance"}
            onClick={() => {
              mapLayerModeSignal.value = "electoral_balance";
            }}
          >
            Saldo (Dir − Esq)
          </button>
          <button
            type="button"
            class={`segmented-btn ${layerMode === "electoral_bloc" ? "is-active" : ""}`}
            aria-pressed={layerMode === "electoral_bloc"}
            title="Pintar mapa pela porcentagem de votos do bloco político"
            onClick={() => {
              mapLayerModeSignal.value = "electoral_bloc";
            }}
          >
            % do Bloco
          </button>
          {hasIndicator && (
            <button
              type="button"
              class={`segmented-btn ${isSwipeModeSignal.value ? "is-active" : ""}`}
              aria-pressed={isSwipeModeSignal.value}
              title="Comparar indicador e voto arrastando uma cortina divisora"
              onClick={() => {
                const next = !isSwipeModeSignal.value;
                isSwipeModeSignal.value = next;
                if (next && mapLayerModeSignal.value === "indicator") {
                  mapLayerModeSignal.value = "electoral_balance";
                }
              }}
            >
              ⇄ Modo Cortina
            </button>
          )}
        </div>

        {layerMode === "electoral_bloc" && (
          <div
            class="layer-pill layer-pill-bloc"
            role="group"
            aria-label="Selecionar bloco político em análise"
          >
            <span class="layer-pill-label">Bloco:</span>
            {(["left", "center", "right"] as const).map((b) => {
              const isSelected = blocSignal.value === b;
              const dotColor =
                b === "left"
                  ? "var(--bloc-left)"
                  : b === "center"
                    ? "var(--bloc-center)"
                    : "var(--bloc-right)";
              return (
                <button
                  key={b}
                  type="button"
                  class={`segmented-btn bloc-choice-btn bloc-${b} ${isSelected ? "is-active" : ""}`}
                  aria-pressed={isSelected}
                  title={`Pintar o mapa com os votos do bloco de ${BLOC_LABELS_PT[b]}`}
                  onClick={() => {
                    blocSignal.value = b;
                  }}
                >
                  <span class="bloc-dot" style={{ backgroundColor: dotColor }} />
                  {BLOC_LABELS_PT[b]}
                </button>
              );
            })}
          </div>
        )}
      </div>

      {isSwipeModeSignal.value && hasIndicator && (
        <MapSwipe primaryMap={mapRef.current} />
      )}

      <MapLegend />
    </section>
  );
}
