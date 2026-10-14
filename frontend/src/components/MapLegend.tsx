import {
  BLOC_LABELS_PT,
  formatCompactValuePt,
  formatIntegerPt,
  formatPctPt,
} from "../lib/format";
import {
  buildLegendBins,
  getElectoralPalette,
  getIndicatorPalette,
  type LegendBin,
} from "../lib/scales";
import {
  activeIndicatorMeta,
  activeLegendBinSignal,
  blocSignal,
  electionMapDataSignal,
  electionUfMapDataSignal,
  geoLevelSignal,
  indicatorMapDataSignal,
  indicatorUfMapDataSignal,
  mapLayerModeSignal,
} from "../state/store";

export function MapLegend() {
  const mode = mapLayerModeSignal.value;
  const bloc = blocSignal.value;
  const isMacro = geoLevelSignal.value === "state";
  const electionMap = isMacro
    ? (electionUfMapDataSignal.value ?? electionMapDataSignal.value)
    : electionMapDataSignal.value;
  const indicatorMap = isMacro
    ? (indicatorUfMapDataSignal.value ?? indicatorMapDataSignal.value)
    : indicatorMapDataSignal.value;
  const indicatorMeta = activeIndicatorMeta.value;
  const activeBin = activeLegendBinSignal.value;

  let title = isMacro
    ? "Saldo Eleitoral por Estado (Direita − Esquerda)"
    : "Saldo Eleitoral (Direita − Esquerda)";
  let unitAndYear = "pontos percentuais · 2026";
  let sourceName = "TSE — Dados Abertos";
  let missingCount = 0;
  let bins: LegendBin[] = [];

  if (mode === "indicator" && indicatorMap && indicatorMeta) {
    title = indicatorMap.indicator.label;
    unitAndYear = `${indicatorMap.indicator.unit} · ref. ${indicatorMap.indicator.ref_year}`;
    sourceName = indicatorMap.indicator.source_name;
    missingCount = indicatorMap.summary.count_missing;
    const palette = getIndicatorPalette(indicatorMeta.theme);
    bins = buildLegendBins(indicatorMap.summary.quantiles_7, palette);
  } else if (electionMap) {
    const palette = getElectoralPalette(
      mode === "indicator" ? "electoral_balance" : mode,
      bloc,
    );
    if (mode === "electoral_bloc") {
      title = `Votos no bloco de ${BLOC_LABELS_PT[bloc]}`;
      unitAndYear = `% dos votos válidos · ${electionMap.election.year}`;
      const q =
        bloc === "left"
          ? electionMap.quantiles.left_share
          : bloc === "center"
            ? (electionMap.quantiles.center_share ?? electionMap.quantiles.right_share)
            : electionMap.quantiles.right_share;
      bins = buildLegendBins(q, palette, 0, 1);
    } else {
      title = "Saldo Eleitoral (Direita − Esquerda)";
      unitAndYear = `Diferença de participação · ${electionMap.election.year}`;
      bins = buildLegendBins(electionMap.quantiles.lr_balance, palette, -1, 1);
    }
  }

  const formatBinTick = (bin: LegendBin): string => {
    if (mode === "indicator" && indicatorMap) {
      return formatCompactValuePt(bin.max, indicatorMap.indicator.unit, false);
    }
    if (mode === "electoral_bloc") {
      return formatPctPt(bin.max, true, 0);
    }
    const pp = Math.round(bin.max * 100);
    return `${pp > 0 ? "+" : ""}${pp}`;
  };

  return (
    <aside class="map-legend" aria-label="Legenda coroplética do mapa">
      <div class="map-legend-header">
        <h2 class="map-legend-title">{title}</h2>
        <span class="map-legend-meta tabular-nums">{unitAndYear}</span>
      </div>

      <div class="map-legend-ramp" role="list">
        {bins.map((bin) => {
          const isActive = activeBin === bin.index;
          return (
            <button
              key={bin.index}
              type="button"
              role="listitem"
              class={`map-legend-bin tabular-nums ${isActive ? "is-active" : ""}`}
              title={`Destacar faixa ${bin.index + 1}`}
              onMouseEnter={() => {
                activeLegendBinSignal.value = bin.index;
              }}
              onMouseLeave={() => {
                activeLegendBinSignal.value = null;
              }}
              onClick={() => {
                activeLegendBinSignal.value =
                  activeLegendBinSignal.value === bin.index ? null : bin.index;
              }}
            >
              <span
                class="map-legend-swatch"
                style={{ backgroundColor: bin.color }}
              />
              <span class="map-legend-tick">{formatBinTick(bin)}</span>
            </button>
          );
        })}
      </div>

      <div class="map-legend-footer">
        <span>Fonte: {sourceName}</span>
        <span class="nodata-badge tabular-nums">
          <span class="nodata-swatch" aria-hidden="true" />
          Sem dado (n = {formatIntegerPt(missingCount)})
        </span>
      </div>
    </aside>
  );
}
