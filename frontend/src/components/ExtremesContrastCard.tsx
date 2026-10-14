import {
  BLOC_LABELS_PT,
  formatIndicatorValuePt,
  formatIntegerPt,
  formatPctPt,
  formatPpDiffPt,
} from "../lib/format";
import {
  activeIndicatorMeta,
  analysisDataSignal,
  blocSignal,
} from "../state/store";

export function ExtremesContrastCard() {
  const analysis = analysisDataSignal.value;
  const indMeta = activeIndicatorMeta.value;
  const bloc = blocSignal.value;
  const contrast = analysis?.extremes_contrast;

  if (!contrast || !indMeta) {
    return null;
  }

  const blocLabel = BLOC_LABELS_PT[bloc];
  const unit = indMeta.unit;

  const botMin = formatIndicatorValuePt(contrast.bottom_indicator_range[0], unit);
  const botMax = formatIndicatorValuePt(contrast.bottom_indicator_range[1], unit);
  const topMin = formatIndicatorValuePt(contrast.top_indicator_range[0], unit);
  const topMax = formatIndicatorValuePt(contrast.top_indicator_range[1], unit);

  const botShareFmt = formatPctPt(contrast.bottom_quintile_share, true);
  const topShareFmt = formatPctPt(contrast.top_quintile_share, true);
  const diffPpFmt = formatPpDiffPt(contrast.diff_pp, false);

  const dotColor =
    bloc === "left"
      ? "var(--bloc-left)"
      : bloc === "center"
        ? "var(--bloc-center)"
        : "var(--bloc-right)";

  return (
    <article
      class="extremes-contrast-card"
      aria-label="Contraste dos Dois Brasis nos Extremos do Indicador"
    >
      <header class="extremes-contrast-header">
        <h3 class="extremes-contrast-title">
          Contraste dos "Dois Brasis" (Extremos do Indicador)
        </h3>
        <span class="extremes-contrast-badge">
          Quintil Superior (20%) vs. Inferior (20%)
        </span>
      </header>

      <p class="extremes-contrast-summary">
        Comparação agregada entre os <strong>20% dos municípios</strong> de menor
        e maior valor em <strong>{indMeta.label}</strong> frente ao voto no
        bloco de <strong>{blocLabel}</strong>:
      </p>

      <div class="extremes-contrast-grid">
        {/* Lado 1: 20% Menores (Base) */}
        <div class="extremes-quintile-box">
          <div class="extremes-quintile-tag">20% Menores (Base)</div>
          <div class="extremes-range-label">
            {botMin} a {botMax}
          </div>
          <div class="extremes-share-val tabular-nums">
            <span class="bloc-dot" style={{ backgroundColor: dotColor }} />
            {botShareFmt}
          </div>
          <div class="extremes-share-bar-container">
            <div
              class="extremes-share-bar"
              style={{
                width: `${(contrast.bottom_quintile_share * 100).toFixed(1)}%`,
                backgroundColor: dotColor,
              }}
            />
          </div>
          <div class="extremes-mun-count">
            {formatIntegerPt(contrast.bottom_municipality_count)} municípios
          </div>
        </div>

        {/* Indicador Central de Variação (Delta) */}
        <div class="extremes-delta-box">
          <span class="extremes-delta-title">Saldo</span>
          <span
            class={`extremes-delta-value tabular-nums ${
              contrast.diff_pp >= 0 ? "is-positive" : "is-negative"
            }`}
          >
            {diffPpFmt}
          </span>
          <span class="extremes-delta-sub">
            {contrast.diff_pp >= 0
              ? `vantagem no topo`
              : `vantagem na base`}
          </span>
        </div>

        {/* Lado 2: 20% Maiores (Topo) */}
        <div class="extremes-quintile-box">
          <div class="extremes-quintile-tag">20% Maiores (Topo)</div>
          <div class="extremes-range-label">
            {topMin} a {topMax}
          </div>
          <div class="extremes-share-val tabular-nums">
            <span class="bloc-dot" style={{ backgroundColor: dotColor }} />
            {topShareFmt}
          </div>
          <div class="extremes-share-bar-container">
            <div
              class="extremes-share-bar"
              style={{
                width: `${(contrast.top_quintile_share * 100).toFixed(1)}%`,
                backgroundColor: dotColor,
              }}
            />
          </div>
          <div class="extremes-mun-count">
            {formatIntegerPt(contrast.top_municipality_count)} municípios
          </div>
        </div>
      </div>

      {contrast.tipping_point_decile && (
        <footer class="extremes-tipping-row">
          <span class="tipping-point-icon">⚡</span>
          <span class="tipping-point-text">
            <strong>Ponto de Inflexão (Decil D{contrast.tipping_point_decile}):</strong>{" "}
            a inclinação do voto acelera ou assume a liderança a partir de{" "}
            <strong>
              {contrast.tipping_point_threshold !== null
                ? formatIndicatorValuePt(contrast.tipping_point_threshold, unit)
                : `D${contrast.tipping_point_decile}`}
            </strong>
            .
          </span>
        </footer>
      )}
    </article>
  );
}
