import {
  BLOC_LABELS_PT,
  formatIndicatorValuePt,
  formatIntegerPt,
  formatPctPt,
} from "../lib/format";
import {
  activeDecileSignal,
  analysisDataSignal,
  blocSignal,
} from "../state/store";

export function DecileBarChart() {
  const analysis = analysisDataSignal.value;
  const bloc = blocSignal.value;
  const activeDecile = activeDecileSignal.value;

  const deciles = analysis?.deciles ?? [];
  if (!analysis || deciles.length === 0) {
    return null;
  }

  const unit = analysis.indicator.unit;
  const fillVar =
    bloc === "left"
      ? "var(--bloc-left)"
      : bloc === "center"
        ? "var(--bloc-center)"
        : "var(--bloc-right)";

  return (
    <div
      class="decile-chart"
      role="list"
      aria-label={`Participação ponderada do bloco de ${BLOC_LABELS_PT[bloc]} por decil de ${analysis.indicator.label}`}
    >
      {deciles.map((d) => {
        const isActive = activeDecile === d.decile;
        const pctWidth = Math.min(100, Math.max(0, d.weighted_share * 100));
        const label =
          d.decile === 1
            ? "D1"
            : d.decile === 10
              ? "D10"
              : `D${d.decile}`;
        const rangeTitle = `Decil ${d.decile} (${formatIntegerPt(d.municipality_count)} mun.): ${formatIndicatorValuePt(d.indicator_min, unit)} a ${formatIndicatorValuePt(d.indicator_max, unit)} · Voto ponderado: ${formatPctPt(d.weighted_share, true)} (média simples: ${formatPctPt(d.unweighted_mean_share, true)})`;

        return (
          <button
            key={d.decile}
            type="button"
            role="listitem"
            class={`decile-row tabular-nums ${isActive ? "is-active" : ""}`}
            title={rangeTitle}
            onMouseEnter={() => {
              activeDecileSignal.value = d.decile;
            }}
            onMouseLeave={() => {
              activeDecileSignal.value = null;
            }}
            onClick={() => {
              activeDecileSignal.value =
                activeDecileSignal.value === d.decile ? null : d.decile;
            }}
          >
            <span class="decile-label">{label}</span>
            <span class="decile-bar-track" aria-hidden="true">
              <span
                class="decile-bar-fill"
                style={{
                  width: `${pctWidth.toFixed(1)}%`,
                  backgroundColor: fillVar,
                }}
              />
            </span>
            <span class="decile-value">{formatPctPt(d.weighted_share, true)}</span>
          </button>
        );
      })}
    </div>
  );
}
