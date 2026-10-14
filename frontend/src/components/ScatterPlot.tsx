import { useEffect, useMemo, useRef, useState } from "preact/hooks";
import { extent, max } from "d3-array";
import { scaleLinear, scaleLog } from "d3-scale";
import {
  BLOC_LABELS_PT,
  formatCompactValuePt,
  formatPctPt,
  formatRhoPt,
} from "../lib/format";
import { getScatterCanvasColors } from "../lib/scales";
import {
  buildSpatialIndex,
  computePointRadius,
  type ScreenScatterPoint,
} from "../lib/spatial";
import {
  analysisDataSignal,
  blocSignal,
  cursorPositionSignal,
  hoveredIbgeSignal,
  hoveredUfSignal,
  selectedIbgeSignal,
  selectedUfSignal,
  themeSignal,
} from "../state/store";

const DEFAULT_SVG_WIDTH = 440;
const SVG_HEIGHT = 260;
const MARGIN = { top: 28, right: 20, bottom: 38, left: 48 };
const PLOT_H = SVG_HEIGHT - MARGIN.top - MARGIN.bottom;

export function ScatterPlot() {
  const wrapperRef = useRef<HTMLDivElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const svgRef = useRef<SVGSVGElement | null>(null);
  const [svgWidth, setSvgWidth] = useState<number>(DEFAULT_SVG_WIDTH);

  useEffect(() => {
    const el = wrapperRef.current;
    if (!el) {
      return;
    }
    const updateWidth = (): void => {
      const w = Math.round(el.clientWidth);
      if (w >= 240) {
        setSvgWidth(w);
      }
    };
    updateWidth();
    if (typeof ResizeObserver !== "undefined") {
      const ro = new ResizeObserver(updateWidth);
      ro.observe(el);
      return () => ro.disconnect();
    }
    return undefined;
  }, []);

  const plotW = Math.max(160, svgWidth - MARGIN.left - MARGIN.right);

  const analysis = analysisDataSignal.value;
  const bloc = blocSignal.value;
  const theme = themeSignal.value;
  const hoveredIbge = hoveredIbgeSignal.value;
  const selectedIbge = selectedIbgeSignal.value;

  const rows = analysis?.scatter.rows ?? [];
  const scaleHint = analysis?.indicator.scale_hint ?? "linear";
  const unit = analysis?.indicator.unit ?? "";

  const geometry = useMemo(() => {
    if (rows.length === 0) {
      return null;
    }

    const firstRow = rows[0];
    const isUf = firstRow !== undefined && typeof firstRow[0] === "string";
    const xValues = rows.map((r) => (isUf ? Number(r[3]) : Number(r[1])));
    const [rawMinX = 0, rawMaxX = 1] = extent(xValues);
    const maxVotes =
      max(rows, (r) => (isUf ? Number(r[5]) : Number(r[3]))) ?? 1;

    const useLog = scaleHint === "log" && rawMinX > 0 && rawMaxX > rawMinX;
    const xScale = useLog
      ? scaleLog()
          .domain([Math.max(1e-3, rawMinX), rawMaxX])
          .range([MARGIN.left, MARGIN.left + plotW])
      : scaleLinear()
          .domain([rawMinX, rawMaxX === rawMinX ? rawMinX + 1 : rawMaxX])
          .nice()
          .range([MARGIN.left, MARGIN.left + plotW]);

    const yScale = scaleLinear()
      .domain([0, 1])
      .range([MARGIN.top + PLOT_H, MARGIN.top]);

    const screenPoints: ScreenScatterPoint[] = rows.map((r) => {
      if (isUf) {
        const ufStr = String(r[0]);
        const ufCode = Number(r[1]);
        const nameStr = String(r[2]);
        const xVal = Number(r[3]);
        const yVal = Number(r[4]);
        const validVotes = Number(r[5]);
        const reg = String(r[6]);
        return {
          cdIbge: ufCode,
          uf: ufStr,
          name: nameStr,
          px: xScale(xVal),
          py: yScale(yVal),
          radius: computePointRadius(validVotes, maxVotes, 9, 20),
          xVal,
          yVal,
          validVotes,
          region: reg,
        };
      }
      const cd = Number(r[0]);
      const xVal = Number(r[1]);
      const yVal = Number(r[2]);
      const validVotes = Number(r[3]);
      const reg = String(r[4]);
      return {
        cdIbge: cd,
        px: xScale(xVal),
        py: yScale(yVal),
        radius: computePointRadius(validVotes, maxVotes),
        xVal,
        yVal,
        validVotes,
        region: reg,
      };
    });

    const byIbge = new Map<number, ScreenScatterPoint>();
    for (const pt of screenPoints) {
      byIbge.set(pt.cdIbge, pt);
    }

    const spatialIndex = buildSpatialIndex(screenPoints);
    const rawXTicks = xScale.ticks(5);
    const xTicks: number[] = [];
    let lastTickPx = -Infinity;
    const minTickGapPx = 74;
    for (const candidate of rawXTicks) {
      const px = xScale(candidate);
      if (
        px >= MARGIN.left + 12 &&
        px <= MARGIN.left + plotW - 16 &&
        px - lastTickPx >= minTickGapPx
      ) {
        xTicks.push(candidate);
        lastTickPx = px;
      }
    }
    const yTicks = [0, 0.25, 0.5, 0.75, 1.0];

    const trendPoints = (analysis?.trendline.points ?? [])
      .filter(([tx]) => !useLog || tx > 0)
      .map(([tx, ty]) => `${xScale(tx).toFixed(1)},${yScale(ty).toFixed(1)}`)
      .join(" ");

    return {
      isUf,
      useLog,
      xScale,
      yScale,
      xTicks,
      yTicks,
      screenPoints,
      byIbge,
      spatialIndex,
      trendPolyline: trendPoints,
    };
  }, [rows, scaleHint, analysis?.trendline.points, plotW]);

  // Draw points onto the background <canvas> (in municipality mode)
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !geometry) {
      return;
    }

    const dpr = window.devicePixelRatio || 1;
    canvas.width = svgWidth * dpr;
    canvas.height = SVG_HEIGHT * dpr;

    const ctx = canvas.getContext("2d");
    if (!ctx) {
      return;
    }

    ctx.save();
    ctx.scale(dpr, dpr);
    ctx.clearRect(0, 0, svgWidth, SVG_HEIGHT);

    // When in UF mode, the 27 points are rendered as interactive labeled SVG elements
    if (geometry.isUf) {
      ctx.restore();
      return;
    }

    const colors = getScatterCanvasColors(theme, bloc);
    ctx.fillStyle = colors.pointFill;
    ctx.strokeStyle = colors.pointStroke;
    ctx.lineWidth = 0.6;

    for (let i = 0; i < geometry.screenPoints.length; i++) {
      const pt = geometry.screenPoints[i];
      if (!pt) {
        continue;
      }
      ctx.beginPath();
      ctx.arc(pt.px, pt.py, pt.radius, 0, Math.PI * 2);
      ctx.fill();
      ctx.stroke();
    }

    ctx.restore();
  }, [geometry, theme, bloc, svgWidth]);

  if (!analysis || !geometry) {
    return null;
  }

  const hoveredUf = hoveredUfSignal.value;
  const selectedUf = selectedUfSignal.value;

  const handleMouseMove = (e: MouseEvent): void => {
    const svg = svgRef.current;
    if (!svg) {
      return;
    }
    const rect = svg.getBoundingClientRect();
    const scaleX = svgWidth / (rect.width || svgWidth);
    const scaleY = SVG_HEIGHT / (rect.height || SVG_HEIGHT);
    const localX = (e.clientX - rect.left) * scaleX;
    const localY = (e.clientY - rect.top) * scaleY;

    cursorPositionSignal.value = { x: e.clientX, y: e.clientY };
    const hit = geometry.spatialIndex.findNearest(
      localX,
      localY,
      geometry.isUf ? 22 : 12,
    );
    if (geometry.isUf) {
      hoveredUfSignal.value = hit?.uf ?? null;
      hoveredIbgeSignal.value = hit ? hit.cdIbge : null;
    } else {
      hoveredIbgeSignal.value = hit ? hit.cdIbge : null;
    }
  };

  const handleMouseLeave = (): void => {
    hoveredIbgeSignal.value = null;
    hoveredUfSignal.value = null;
  };

  const handleClick = (): void => {
    if (geometry.isUf) {
      if (hoveredUfSignal.value) {
        selectedUfSignal.value = hoveredUfSignal.value;
      }
    } else {
      if (hoveredIbgeSignal.value !== null) {
        selectedIbgeSignal.value = hoveredIbgeSignal.value;
      }
    }
  };

  const hoveredPoint =
    hoveredIbge !== null ? geometry.byIbge.get(hoveredIbge) : undefined;
  const selectedPoint =
    selectedIbge !== null ? geometry.byIbge.get(selectedIbge) : undefined;

  return (
    <div
      ref={wrapperRef}
      class="scatter-wrapper"
      aria-label="Gráfico de dispersão municipal"
    >
      <canvas ref={canvasRef} class="scatter-canvas" />

      <svg
        ref={svgRef}
        class="scatter-svg tabular-nums"
        viewBox={`0 0 ${svgWidth} ${SVG_HEIGHT}`}
        onMouseMove={handleMouseMove}
        onMouseLeave={handleMouseLeave}
        onClick={handleClick}
      >
        {/* Linhas horizontais de grade e eixo Y */}
        {geometry.yTicks.map((yt) => {
          const py = geometry.yScale(yt);
          return (
            <g key={yt}>
              <line
                x1={MARGIN.left}
                x2={MARGIN.left + plotW}
                y1={py}
                y2={py}
                stroke="var(--border-subtle)"
                stroke-width="1"
              />
              <text
                x={MARGIN.left - 6}
                y={py + 4}
                text-anchor="end"
                font-size="10"
                fill="var(--text-muted)"
              >
                {formatPctPt(yt, true, 0)}
              </text>
            </g>
          );
        })}

        {/* Eixo X e ticks */}
        {geometry.xTicks.map((xt) => {
          const px = geometry.xScale(xt);
          return (
            <g key={xt}>
              <line
                x1={px}
                x2={px}
                y1={MARGIN.top + PLOT_H}
                y2={MARGIN.top + PLOT_H + 4}
                stroke="var(--border-strong)"
              />
              <text
                x={px}
                y={MARGIN.top + PLOT_H + 15}
                text-anchor="middle"
                font-size="10"
                fill="var(--text-muted)"
              >
                {formatCompactValuePt(xt, unit)}
              </text>
            </g>
          );
        })}

        {/* Rótulos dos eixos */}
        <text
          x={MARGIN.left + plotW / 2}
          y={SVG_HEIGHT - 6}
          text-anchor="middle"
          font-size="11"
          font-weight="600"
          fill="var(--text-secondary)"
        >
          {analysis.indicator.label} ({analysis.indicator.unit})
          {geometry.useLog ? " · escala log" : ""}
        </text>

        <text
          x={12}
          y={MARGIN.top + PLOT_H / 2}
          text-anchor="middle"
          font-size="11"
          font-weight="600"
          fill="var(--text-secondary)"
          transform={`rotate(-90 12 ${MARGIN.top + PLOT_H / 2})`}
        >
          % Votos {BLOC_LABELS_PT[bloc]}
        </text>

        {/* Linha de tendência (regressão calculada pelo backend) */}
        {geometry.trendPolyline && (
          <polyline
            fill="none"
            stroke="var(--text-primary)"
            stroke-width="2"
            stroke-dasharray="4 3"
            points={geometry.trendPolyline}
          />
        )}

        {/* Pontos dos 27 estados com círculos rotulados com sigla da UF */}
        {geometry.isUf &&
          geometry.screenPoints.map((pt) => {
            const isSel = selectedUf === pt.uf;
            const isHov = hoveredUf === pt.uf;
            return (
              <g key={pt.uf ?? pt.cdIbge} class="scatter-uf-group">
                <circle
                  cx={pt.px}
                  cy={pt.py}
                  r={pt.radius}
                  fill="var(--surface-elevated)"
                  stroke={
                    isSel
                      ? "var(--accent-ui)"
                      : isHov
                        ? "var(--map-hover-stroke)"
                        : "var(--border-strong)"
                  }
                  stroke-width={isSel ? 2.8 : isHov ? 2.2 : 1.2}
                />
                <text
                  x={pt.px}
                  y={pt.py + 3.5}
                  text-anchor="middle"
                  font-size="9"
                  font-weight="700"
                  fill="var(--text-primary)"
                  pointer-events="none"
                >
                  {pt.uf}
                </text>
              </g>
            );
          })}

        {/* Destaque do município selecionado (modo municipal) */}
        {!geometry.isUf && selectedPoint && (
          <circle
            cx={selectedPoint.px}
            cy={selectedPoint.py}
            r={selectedPoint.radius + 3}
            fill="none"
            stroke="var(--accent-ui)"
            stroke-width="2.5"
          />
        )}

        {/* Destaque do município sob hover (modo municipal) */}
        {!geometry.isUf && hoveredPoint && (
          <circle
            cx={hoveredPoint.px}
            cy={hoveredPoint.py}
            r={hoveredPoint.radius + 2.5}
            fill="var(--surface-elevated)"
            stroke="var(--map-hover-stroke)"
            stroke-width="2.5"
          />
        )}
      </svg>

      <div class="correlation-badge tabular-nums">
        Spearman ρ = {formatRhoPt(analysis.correlation.spearman_rho)} (
        {analysis.correlation.strength_label})
      </div>
    </div>
  );
}
