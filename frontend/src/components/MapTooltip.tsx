import {
  formatIndicatorValuePt,
  formatIntegerPt,
  formatPctPt,
} from "../lib/format";
import {
  activeIndicatorMeta,
  cursorPositionSignal,
  electionByIbgeMap,
  electionByUfMap,
  geoLevelSignal,
  hoveredIbgeSignal,
  hoveredUfSignal,
  indicatorValueByIbgeMap,
  indicatorValueByUfMap,
  metaDataSignal,
  municipalityDirectorySignal,
} from "../state/store";

export function MapTooltip() {
  const isMacro = geoLevelSignal.value === "state";
  const hoveredUf = hoveredUfSignal.value;
  const hoveredIbge = hoveredIbgeSignal.value;

  if (isMacro ? hoveredUf === null : hoveredIbge === null) {
    return null;
  }

  const pos = cursorPositionSignal.value;
  const indMeta = activeIndicatorMeta.value;
  const meta = metaDataSignal.value;

  const viewportW = typeof window !== "undefined" ? window.innerWidth : 1280;
  const viewportH = typeof window !== "undefined" ? window.innerHeight : 800;

  const tooltipW = 268;
  const tooltipH = 124;
  const offset = 14;

  const left =
    pos.x + offset + tooltipW > viewportW - 12
      ? Math.max(12, pos.x - tooltipW - offset)
      : pos.x + offset;
  const top =
    pos.y + offset + tooltipH > viewportH - 12
      ? Math.max(12, pos.y - tooltipH - offset)
      : pos.y + offset;

  if (isMacro && hoveredUf !== null) {
    const ufInfo = electionByUfMap.value.get(hoveredUf);
    const indVal = indMeta
      ? indicatorValueByUfMap.value.get(hoveredUf)
      : undefined;
    const ufMeta = meta?.ufs.find((u) => u.uf === hoveredUf);
    const stateName = ufMeta?.name ?? ufInfo?.name ?? hoveredUf;
    const region = ufMeta?.region ?? "";

    const leftPct = ufInfo ? ufInfo.leftShare * 100 : 0;
    const centerPct = ufInfo ? ufInfo.centerShare * 100 : 0;
    const rightPct = ufInfo ? ufInfo.rightShare * 100 : 0;

    return (
      <div
        class="map-tooltip"
        role="status"
        style={{
          left: `${left}px`,
          top: `${top}px`,
        }}
      >
        <div class="tooltip-header">
          <p class="tooltip-mun-name">
            {stateName} ({hoveredUf})
          </p>
          <span class="tooltip-region">{region}</span>
        </div>

        {ufInfo ? (
          <>
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
          </>
        ) : (
          <div class="bloc-labels-row">Sem votos apurados no estado</div>
        )}

        {indMeta && (
          <div class="tooltip-indicator-line tabular-nums">
            <span>{indMeta.label}:</span>
            <strong>{formatIndicatorValuePt(indVal, indMeta.unit)}</strong>
          </div>
        )}

        <div class="tooltip-hint tabular-nums">
          {ufInfo
            ? `${formatIntegerPt(ufInfo.validVotes)} votos válidos · Clique para selecionar`
            : "Clique para selecionar o estado"}
        </div>
      </div>
    );
  }

  const munInfo = hoveredIbge !== null ? municipalityDirectorySignal.value.get(hoveredIbge) : undefined;
  const electionRow = hoveredIbge !== null ? electionByIbgeMap.value.get(hoveredIbge) : undefined;
  const indVal = indMeta && hoveredIbge !== null
    ? indicatorValueByIbgeMap.value.get(hoveredIbge)
    : undefined;

  const leftPct = electionRow ? electionRow.leftShare * 100 : 0;
  const centerPct = electionRow ? electionRow.centerShare * 100 : 0;
  const rightPct = electionRow ? electionRow.rightShare * 100 : 0;

  return (
    <div
      class="map-tooltip"
      role="status"
      style={{
        left: `${left}px`,
        top: `${top}px`,
      }}
    >
      <div class="tooltip-header">
        <p class="tooltip-mun-name">
          {munInfo
            ? `${munInfo.name} — ${munInfo.uf}`
            : `Município ${hoveredIbge}`}
        </p>
        <span class="tooltip-region">{munInfo?.region ?? ""}</span>
      </div>

      {electionRow ? (
        <>
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
            <span>Esq {formatPctPt(electionRow.leftShare, true)}</span>
            <span>Cen {formatPctPt(electionRow.centerShare, true)}</span>
            <span>Dir {formatPctPt(electionRow.rightShare, true)}</span>
          </div>
        </>
      ) : (
        <div class="bloc-labels-row">Sem votos apurados no filtro</div>
      )}

      {indMeta && (
        <div class="tooltip-indicator-line tabular-nums">
          <span>{indMeta.label}:</span>
          <strong>{formatIndicatorValuePt(indVal, indMeta.unit)}</strong>
        </div>
      )}

      <div class="tooltip-hint tabular-nums">
        {electionRow
          ? `${formatIntegerPt(electionRow.validVotes)} votos válidos · Clique para abrir ficha`
          : "Clique para abrir a ficha completa"}
      </div>
    </div>
  );
}
