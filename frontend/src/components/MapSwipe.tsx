import { useEffect, useRef } from "preact/hooks";
import maplibregl, {
  type ExpressionSpecification,
  type StyleSpecification,
} from "maplibre-gl";
import {
  applyMetricToMap,
  buildMapLibreColorExpression,
  encodeIndicatorRowsForMap,
  getIndicatorPalette,
  getThemeMapColors,
} from "../lib/scales";
import {
  activeIndicatorMeta,
  indicatorMapDataSignal,
  metaDataSignal,
  swipePositionSignal,
  themeSignal,
} from "../state/store";
import type { IndicatorMapRow } from "../types/api";

interface MapSwipeProps {
  primaryMap: maplibregl.Map | null;
}

export function MapSwipe({ primaryMap }: MapSwipeProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const secondaryMapRef = useRef<maplibregl.Map | null>(null);
  const isSyncingRef = useRef<boolean>(false);
  const isDraggingRef = useRef<boolean>(false);

  const swipePos = swipePositionSignal.value;
  const indMeta = activeIndicatorMeta.value;
  const indData = indicatorMapDataSignal.value;

  // Initialize secondary map for Indicator view
  useEffect(() => {
    const container = containerRef.current;
    if (!container || secondaryMapRef.current || !primaryMap) {
      return;
    }

    const themeColors = getThemeMapColors(themeSignal.value);
    const dv = metaDataSignal.value?.dataset_version ?? 1;
    const origin = window.location.origin;

    const style: StyleSpecification = {
      version: 8,
      sources: {
        "territorio-mun-swipe": {
          type: "vector",
          tiles: [`${origin}/tiles/municipalities/{z}/{x}/{y}.pbf?v=${dv}`],
          minzoom: 0,
          maxzoom: 12,
        },
      },
      layers: [
        {
          id: "background-swipe",
          type: "background",
          paint: {
            "background-color": themeColors.background,
          },
        },
        {
          id: "mun-fill-swipe",
          type: "fill",
          source: "territorio-mun-swipe",
          "source-layer": "municipalities",
          paint: {
            "fill-color": themeColors.noData,
            "fill-outline-color": themeColors.munStroke,
            "fill-opacity": 0.94,
          },
        },
        {
          id: "mun-border-swipe",
          type: "line",
          source: "territorio-mun-swipe",
          "source-layer": "municipalities",
          minzoom: 5,
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
          id: "uf-border-swipe",
          type: "line",
          source: "territorio-mun-swipe",
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
      ],
    };

    const secMap = new maplibregl.Map({
      container,
      style,
      center: primaryMap.getCenter(),
      zoom: primaryMap.getZoom(),
      bearing: primaryMap.getBearing(),
      pitch: primaryMap.getPitch(),
      attributionControl: false,
    });

    secMap.on("load", () => {
      syncIndicatorLayer();
    });

    // Synchronize cameras between primary and secondary map
    const syncFromPrimary = (): void => {
      if (isSyncingRef.current || !secMap) {
        return;
      }
      isSyncingRef.current = true;
      secMap.jumpTo({
        center: primaryMap.getCenter(),
        zoom: primaryMap.getZoom(),
        bearing: primaryMap.getBearing(),
        pitch: primaryMap.getPitch(),
      });
      isSyncingRef.current = false;
    };

    const syncFromSecondary = (): void => {
      if (isSyncingRef.current || !primaryMap) {
        return;
      }
      isSyncingRef.current = true;
      primaryMap.jumpTo({
        center: secMap.getCenter(),
        zoom: secMap.getZoom(),
        bearing: secMap.getBearing(),
        pitch: secMap.getPitch(),
      });
      isSyncingRef.current = false;
    };

    primaryMap.on("move", syncFromPrimary);
    secMap.on("move", syncFromSecondary);

    secondaryMapRef.current = secMap;

    return () => {
      primaryMap.off("move", syncFromPrimary);
      secMap.remove();
      secondaryMapRef.current = null;
    };
  }, [primaryMap]);

  // Update secondary map's indicator paint when data changes
  const syncIndicatorLayer = (): void => {
    const secMap = secondaryMapRef.current;
    if (!secMap || !secMap.isStyleLoaded() || !indData || !indMeta) {
      return;
    }
    const themeColors = getThemeMapColors(themeSignal.value);
    const palette = getIndicatorPalette(indMeta.theme);
    const munRows = indData.rows.filter(
      (r): r is IndicatorMapRow => typeof r[0] === "number",
    );
    const encoded = encodeIndicatorRowsForMap(
      munRows,
      indMeta.value_type,
    );
    const quantiles = indData.summary.quantiles_7;
    const colorExpr = buildMapLibreColorExpression(
      quantiles,
      palette,
      themeColors.noData,
    );
    secMap.setPaintProperty(
      "mun-fill-swipe",
      "fill-color",
      colorExpr as ExpressionSpecification,
    );
    applyMetricToMap(secMap, encoded.numericRows, null);
  };

  useEffect(() => {
    syncIndicatorLayer();
  }, [indData, indMeta, themeSignal.value]);

  // Pointer drag handling for the swipe divider
  const handlePointerDown = (e: PointerEvent): void => {
    (e.target as HTMLElement).setPointerCapture(e.pointerId);
    isDraggingRef.current = true;
  };

  const handlePointerMove = (e: PointerEvent): void => {
    if (!isDraggingRef.current || !containerRef.current) {
      return;
    }
    const rect = containerRef.current.parentElement?.getBoundingClientRect();
    if (!rect || rect.width === 0) {
      return;
    }
    const x = e.clientX - rect.left;
    const clamped = Math.max(5, Math.min(95, (x / rect.width) * 100));
    swipePositionSignal.value = Math.round(clamped);
  };

  const handlePointerUp = (e: PointerEvent): void => {
    isDraggingRef.current = false;
    try {
      (e.target as HTMLElement).releasePointerCapture(e.pointerId);
    } catch {
      // Ignored
    }
  };

  const handleKeyDown = (e: KeyboardEvent): void => {
    if (e.key === "ArrowLeft") {
      e.preventDefault();
      swipePositionSignal.value = Math.max(5, swipePositionSignal.value - 5);
    } else if (e.key === "ArrowRight") {
      e.preventDefault();
      swipePositionSignal.value = Math.min(95, swipePositionSignal.value + 5);
    }
  };

  return (
    <>
      {/* Camada do mapa secundário (Indicador), cortada à esquerda */}
      <div
        ref={containerRef}
        class="maplibre-swipe-container"
        style={{
          clipPath: `polygon(0 0, ${swipePos}% 0, ${swipePos}% 100%, 0 100%)`,
        }}
        aria-hidden="true"
      />

      {/* Barra divisora arrastável (Cortina) */}
      <div
        class="map-swipe-divider"
        style={{ left: `${swipePos}%` }}
        role="slider"
        aria-label="Divisor de comparação entre indicador e votação"
        aria-valuemin={5}
        aria-valuemax={95}
        aria-valuenow={swipePos}
        tabIndex={0}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onKeyDown={handleKeyDown}
      >
        <div class="map-swipe-handle">
          <span class="map-swipe-arrows">⇄</span>
        </div>
      </div>

      {/* Badges indicativas em cima do mapa */}
      <div class="map-swipe-badges" aria-hidden="true">
        <div class="swipe-badge swipe-badge-left">
          <span>📊 Indicador:</span> <strong>{indMeta?.label}</strong>
        </div>
        <div class="swipe-badge swipe-badge-right">
          <span>🗳️ Votação:</span> <strong>Eleição 2026</strong>
        </div>
      </div>
    </>
  );
}
