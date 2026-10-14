import { useEffect, useState } from "preact/hooks";
import type { Map as MapLibreMap } from "maplibre-gl";
import { formatCompactValuePt, formatPctPt } from "../lib/format";
import {
  activeIndicatorMeta,
  drillDownToState,
  electionByUfMap,
  hoveredUfSignal,
  indicatorValueByUfMap,
  mapLayerModeSignal,
  selectedUfSignal,
} from "../state/store";

interface UfCoordConfig {
  uf: string;
  name: string;
  center: [number, number];
  callout?: [number, number];
  anchor?: [number, number];
}

const UF_COORDS: readonly UfCoordConfig[] = [
  // 19 Estados com rótulos internos no centróide
  { uf: "AC", name: "Acre", center: [-70.47, -9.22] },
  { uf: "AM", name: "Amazonas", center: [-64.66, -4.17] },
  { uf: "RR", name: "Roraima", center: [-61.39, 2.08] },
  { uf: "AP", name: "Amapá", center: [-51.96, 1.44] },
  { uf: "PA", name: "Pará", center: [-53.08, -4.0] },
  { uf: "RO", name: "Rondônia", center: [-62.84, -10.92] },
  { uf: "MT", name: "Mato Grosso", center: [-55.91, -12.98] },
  { uf: "MS", name: "Mato Grosso do Sul", center: [-54.85, -20.35] },
  { uf: "TO", name: "Tocantins", center: [-48.33, -10.17] },
  { uf: "GO", name: "Goiás", center: [-49.63, -16.06] },
  { uf: "MA", name: "Maranhão", center: [-45.29, -5.09] },
  { uf: "PI", name: "Piauí", center: [-42.98, -7.41] },
  { uf: "CE", name: "Ceará", center: [-39.61, -5.1] },
  { uf: "BA", name: "Bahia", center: [-41.73, -12.5] },
  { uf: "MG", name: "Minas Gerais", center: [-44.69, -18.48] },
  { uf: "SP", name: "São Paulo", center: [-48.72, -22.29] },
  { uf: "PR", name: "Paraná", center: [-51.61, -24.65] },
  { uf: "SC", name: "Santa Catarina", center: [-50.47, -27.26] },
  { uf: "RS", name: "Rio Grande do Sul", center: [-53.33, -29.75] },

  // 8 Estados pequenos/costeiros com callout externo e seta apontadora
  {
    uf: "RN",
    name: "Rio Grande do Norte",
    center: [-36.67, -5.84],
    callout: [-33.2, -5.2],
    anchor: [-35.6, -5.6],
  },
  {
    uf: "PB",
    name: "Paraíba",
    center: [-36.83, -7.13],
    callout: [-32.8, -6.8],
    anchor: [-35.3, -7.1],
  },
  {
    uf: "PE",
    name: "Pernambuco",
    center: [-38.02, -8.33],
    callout: [-32.8, -8.4],
    anchor: [-35.8, -8.3],
  },
  {
    uf: "AL",
    name: "Alagoas",
    center: [-36.63, -9.51],
    callout: [-33.2, -9.8],
    anchor: [-35.8, -9.5],
  },
  {
    uf: "SE",
    name: "Sergipe",
    center: [-37.45, -10.58],
    callout: [-33.6, -11.2],
    anchor: [-36.8, -10.7],
  },
  {
    uf: "DF",
    name: "Distrito Federal",
    center: [-47.79, -15.78],
    callout: [-44.6, -14.8],
    anchor: [-47.6, -15.7],
  },
  {
    uf: "ES",
    name: "Espírito Santo",
    center: [-40.67, -19.58],
    callout: [-37.0, -19.6],
    anchor: [-39.8, -19.6],
  },
  {
    uf: "RJ",
    name: "Rio de Janeiro",
    center: [-42.67, -22.2],
    callout: [-38.6, -22.5],
    anchor: [-41.8, -22.2],
  },
];

interface Point2D {
  x: number;
  y: number;
}

interface ProjectedState {
  center: Point2D;
  callout?: Point2D;
  anchor?: Point2D;
}

interface StateLabelsOverlayProps {
  map: MapLibreMap | null;
}

export function StateLabelsOverlay({ map }: StateLabelsOverlayProps) {
  const [projected, setProjected] = useState<Record<string, ProjectedState>>({});

  useEffect(() => {
    if (!map) {
      return;
    }

    const updateProjection = (): void => {
      const next: Record<string, ProjectedState> = {};
      for (const item of UF_COORDS) {
        const centerPt = map.project(item.center);
        const itemProjected: ProjectedState = {
          center: { x: Math.round(centerPt.x), y: Math.round(centerPt.y) },
        };
        if (item.callout) {
          const calloutPt = map.project(item.callout);
          itemProjected.callout = {
            x: Math.round(calloutPt.x),
            y: Math.round(calloutPt.y),
          };
        }
        if (item.anchor) {
          const anchorPt = map.project(item.anchor);
          itemProjected.anchor = {
            x: Math.round(anchorPt.x),
            y: Math.round(anchorPt.y),
          };
        }
        next[item.uf] = itemProjected;
      }
      setProjected(next);
    };

    updateProjection();
    map.on("move", updateProjection);
    map.on("zoom", updateProjection);
    map.on("resize", updateProjection);

    return () => {
      map.off("move", updateProjection);
      map.off("zoom", updateProjection);
      map.off("resize", updateProjection);
    };
  }, [map]);

  const electoralMap = electionByUfMap.value;
  const indicatorMap = indicatorValueByUfMap.value;
  const indMeta = activeIndicatorMeta.value;
  const isIndicatorLayer = mapLayerModeSignal.value === "indicator";
  const hoveredUf = hoveredUfSignal.value;
  const selectedUf = selectedUfSignal.value;

  const handleStateClick = (uf: string, e: MouseEvent): void => {
    e.stopPropagation();
    selectedUfSignal.value = uf;
  };

  const handleStateDoubleClick = (uf: string, e: MouseEvent): void => {
    e.stopPropagation();
    drillDownToState(uf);
  };

  const handleMouseEnter = (uf: string): void => {
    hoveredUfSignal.value = uf;
  };

  const handleMouseLeave = (uf: string): void => {
    if (hoveredUfSignal.value === uf) {
      hoveredUfSignal.value = null;
    }
  };

  return (
    <div
      class="state-labels-overlay"
      aria-label="Rótulos e indicadores dos estados brasileiros"
    >
      {/* Camada SVG para as linhas e setas apontadoras dos callouts */}
      <svg class="state-leader-lines-svg" aria-hidden="true">
        <defs>
          <marker
            id="state-arrowhead-left"
            viewBox="0 0 10 10"
            refX="6"
            refY="5"
            markerWidth="6"
            markerHeight="6"
            orient="auto-start-reverse"
          >
            <path d="M 0 1.5 L 8 5 L 0 8.5 z" class="state-arrow-path" />
          </marker>
        </defs>

        {UF_COORDS.map((item) => {
          if (!item.callout) {
            return null;
          }
          const proj = projected[item.uf];
          if (!proj?.callout) {
            return null;
          }
          const start = proj.callout;
          const target = proj.anchor ?? proj.center;
          const isHighlighted =
            hoveredUf === item.uf || selectedUf === item.uf;

          return (
            <g
              key={`line-${item.uf}`}
              class={`state-leader-group ${isHighlighted ? "is-highlighted" : ""}`}
            >
              <line
                x1={start.x}
                y1={start.y}
                x2={target.x}
                y2={target.y}
                class="state-leader-line"
                marker-end="url(#state-arrowhead-left)"
              />
              <circle
                cx={target.x}
                cy={target.y}
                r="3"
                class="state-anchor-dot"
              />
            </g>
          );
        })}
      </svg>

      {/* Camada HTML para os badges com tipografia e contraste */}
      <div class="state-badges-container">
        {UF_COORDS.map((item) => {
          const proj = projected[item.uf];
          if (!proj) {
            return null;
          }

          const pos = proj.callout ?? proj.center;
          const isCallout = Boolean(proj.callout);
          const ufData = electoralMap.get(item.uf);
          const indVal = indicatorMap.get(item.uf);
          const isHovered = hoveredUf === item.uf;
          const isSelected = selectedUf === item.uf;

          let blocClass = "bloc-neutral";
          let shareText = "--";
          if (ufData) {
            blocClass = `bloc-${ufData.leadingBloc}`;
            shareText = formatPctPt(ufData.leadingShare, true, 0);
          }

          let valueLabel = shareText;
          if (isIndicatorLayer && indVal !== undefined && indVal !== null) {
            valueLabel = formatCompactValuePt(indVal, indMeta?.unit ?? "");
          }

          const accessibleTitle = ufData
            ? `${item.name} (${item.uf}): liderança do bloco ${ufData.leadingBloc} com ${formatPctPt(ufData.leadingShare, true)}. Clique para selecionar ou duplo-clique para explorar os municípios.`
            : `${item.name} (${item.uf})`;

          return (
            <button
              key={`badge-${item.uf}`}
              type="button"
              class={`state-badge ${isCallout ? "is-callout" : "is-interior"} ${blocClass} ${
                isHovered ? "is-hovered" : ""
              } ${isSelected ? "is-selected" : ""}`}
              style={{
                transform: `translate3d(${pos.x}px, ${pos.y}px, 0)`,
              }}
              title={accessibleTitle}
              aria-label={accessibleTitle}
              onClick={(e) => handleStateClick(item.uf, e)}
              onDblClick={(e) => handleStateDoubleClick(item.uf, e)}
              onMouseEnter={() => handleMouseEnter(item.uf)}
              onMouseLeave={() => handleMouseLeave(item.uf)}
            >
              <span class="state-badge-uf">{item.uf}</span>
              <span class="state-badge-val tabular-nums">{valueLabel}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
