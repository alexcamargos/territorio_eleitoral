import {
  BLOC_LABELS_PT,
  formatIndicatorValuePt,
  formatIntegerPt,
  formatPctPt,
} from "../lib/format";
import {
  activeIndicatorMeta,
  drillDownToState,
  electionByUfMap,
  indicatorValueByUfMap,
  metaDataSignal,
  selectedUfSignal,
} from "../state/store";

export function StateFocusCard() {
  const selectedUf = selectedUfSignal.value;
  if (!selectedUf) {
    return null;
  }

  const ufInfo = electionByUfMap.value.get(selectedUf);
  const indMeta = activeIndicatorMeta.value;
  const indVal = indMeta ? indicatorValueByUfMap.value.get(selectedUf) : null;
  const meta = metaDataSignal.value;
  const ufMeta = meta?.ufs.find((u) => u.uf === selectedUf);

  const stateName = ufMeta?.name ?? ufInfo?.name ?? selectedUf;
  const region = ufMeta?.region ?? "";

  const leftPct = ufInfo ? ufInfo.leftShare * 100 : 0;
  const centerPct = ufInfo ? ufInfo.centerShare * 100 : 0;
  const rightPct = ufInfo ? ufInfo.rightShare * 100 : 0;

  const handleDrillDown = (): void => {
    drillDownToState(selectedUf);
  };

  const handleClose = (): void => {
    selectedUfSignal.value = null;
  };

  return (
    <div
      class="state-focus-card"
      role="region"
      aria-label={`Destaque do Estado de ${stateName}`}
    >
      <div class="state-focus-header">
        <div>
          <h3 class="state-focus-title">
            {stateName} ({selectedUf})
          </h3>
          <span class="state-focus-region">{region}</span>
        </div>
        <button
          type="button"
          class="state-focus-close-btn"
          aria-label="Fechar destaque do estado"
          onClick={handleClose}
        >
          ✕
        </button>
      </div>

      {ufInfo ? (
        <div class="state-focus-body">
          <div class="state-focus-summary">
            <span class="state-focus-bloc-lead">
              Liderança:{" "}
              <strong>{BLOC_LABELS_PT[ufInfo.leadingBloc]}</strong> (
              {formatPctPt(ufInfo.leadingShare, true)})
            </span>
            <span class="state-focus-turnout tabular-nums">
              Comparecimento: {formatPctPt(ufInfo.turnoutPct, true)} ·{" "}
              {formatIntegerPt(ufInfo.validVotes)} votos válidos
            </span>
          </div>

          <div class="bloc-bar-tri" aria-hidden="true">
            <div
              class="bloc-seg-left"
              style={{ width: `${leftPct.toFixed(1)}%` }}
            />
            <div
              class="bloc-seg-center"
              style={{ width: `${centerPct.toFixed(1)}%` }}
            />
            <div
              class="bloc-seg-right"
              style={{ width: `${rightPct.toFixed(1)}%` }}
            />
          </div>

          <div class="bloc-labels-row tabular-nums">
            <span>Esq {formatPctPt(ufInfo.leftShare, true)}</span>
            <span>Cen {formatPctPt(ufInfo.centerShare, true)}</span>
            <span>Dir {formatPctPt(ufInfo.rightShare, true)}</span>
          </div>

          {indMeta && (
            <div class="state-focus-indicator tabular-nums">
              <span class="state-focus-indicator-label">
                {indMeta.label}:
              </span>
              <strong class="state-focus-indicator-val">
                {formatIndicatorValuePt(indVal, indMeta.unit)}
              </strong>
            </div>
          )}

          <button
            type="button"
            class="state-focus-drilldown-btn"
            onClick={handleDrillDown}
          >
            Explorar municípios de {selectedUf} →
          </button>
        </div>
      ) : (
        <div class="state-focus-body">
          <p>Carregando dados eleitorais de {stateName}...</p>
        </div>
      )}
    </div>
  );
}
