import { useEffect } from "preact/hooks";
import {
  BLOC_LABELS_PT,
  formatIndicatorValuePt,
  formatIntegerPt,
  formatPctPt,
} from "../lib/format";
import { apiClient } from "../services/apiClient";
import {
  analysisDataSignal,
  blocSignal,
  municipalityDirectorySignal,
  registerMunicipalitiesInDirectory,
  selectedIbgeSignal,
  selectedUfSignal,
} from "../state/store";

export function AccessibleDataTable() {
  const analysis = analysisDataSignal.value;
  const bloc = blocSignal.value;
  const directory = municipalityDirectorySignal.value;

  const firstRow = analysis?.scatter.rows[0];
  const isUf = firstRow !== undefined && typeof firstRow[0] === "string";

  const sortedRows = analysis
    ? isUf
      ? [...analysis.scatter.rows].sort((a, b) =>
          Number(a[3]) !== Number(b[3])
            ? Number(a[3]) - Number(b[3])
            : String(a[0]).localeCompare(String(b[0])),
        )
      : [...analysis.scatter.rows].sort((a, b) =>
          Number(a[1]) !== Number(b[1])
            ? Number(a[1]) - Number(b[1])
            : Number(a[0]) - Number(b[0]),
        )
    : [];
  const bottom10 = sortedRows.slice(0, 10);
  const top10 = sortedRows.slice(-10).reverse();

  useEffect(() => {
    if (!analysis || isUf) {
      return;
    }
    const extremeIds = [...top10, ...bottom10].map((r) => Number(r[0]));
    const missingIds = extremeIds.filter(
      (id) => !municipalityDirectorySignal.value.has(id),
    );
    if (missingIds.length === 0) {
      return;
    }
    let cancelled = false;
    Promise.allSettled(
      missingIds.map((id) => apiClient.fetchMunicipalityProfile(id)),
    ).then((results) => {
      if (cancelled) {
        return;
      }
      const resolved = [];
      for (const res of results) {
        if (res.status === "fulfilled") {
          const m = res.value.municipality;
          resolved.push({
            cd_ibge: m.cd_ibge,
            name: m.name,
            uf: m.uf,
            region: m.region,
          });
        }
      }
      if (resolved.length > 0) {
        registerMunicipalitiesInDirectory(resolved);
      }
    });
    return () => {
      cancelled = true;
    };
  }, [analysis?.indicator.code, analysis?.scope.uf, isUf]);

  if (!analysis) {
    return null;
  }

  const unit = analysis.indicator.unit;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
      <table
        class="accessible-table tabular-nums"
        aria-label={`Tabela dos 10 decis ponderados de ${analysis.indicator.label}`}
      >
        <thead>
          <tr>
            <th scope="col">Decil</th>
            <th scope="col">Faixa ({unit})</th>
            <th scope="col">Mun.</th>
            <th scope="col">Voto {BLOC_LABELS_PT[bloc]} (Pond.)</th>
          </tr>
        </thead>
        <tbody>
          {analysis.deciles.map((d) => (
            <tr key={d.decile}>
              <td>D{d.decile}</td>
              <td>
                {formatIndicatorValuePt(d.indicator_min, unit)} –{" "}
                {formatIndicatorValuePt(d.indicator_max, unit)}
              </td>
              <td>{formatIntegerPt(d.municipality_count)}</td>
              <td>
                <strong>{formatPctPt(d.weighted_share, true)}</strong>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {sortedRows.length > 0 && (
        <table
          class="accessible-table tabular-nums"
          aria-label={
            isUf
              ? `Estados nos extremos de ${analysis.indicator.label}`
              : `20 municípios nos extremos de ${analysis.indicator.label}`
          }
        >
          <thead>
            <tr>
              <th scope="col">Extremo</th>
              <th scope="col">{isUf ? "Estado" : "Município"}</th>
              <th scope="col">{analysis.indicator.label}</th>
              <th scope="col">Voto {BLOC_LABELS_PT[bloc]}</th>
            </tr>
          </thead>
          <tbody>
            {top10.map((r, idx) => {
              if (isUf) {
                const uf = String(r[0]);
                const name = String(r[2]);
                const xVal = Number(r[3]);
                const yVal = Number(r[4]);
                return (
                  <tr key={`top-${uf}`}>
                    <td>{idx + 1}º Maior</td>
                    <td>
                      <button
                        type="button"
                        class="table-link-btn"
                        onClick={() => {
                          selectedUfSignal.value = uf;
                        }}
                      >
                        {name} ({uf})
                      </button>
                    </td>
                    <td>{formatIndicatorValuePt(xVal, unit)}</td>
                    <td>{formatPctPt(yVal, true)}</td>
                  </tr>
                );
              }
              const cd = Number(r[0]);
              const info = directory.get(cd);
              return (
                <tr key={`top-${cd}`}>
                  <td>{idx + 1}º Maior</td>
                  <td>
                    <button
                      type="button"
                      class="table-link-btn"
                      onClick={() => {
                        selectedIbgeSignal.value = cd;
                      }}
                    >
                      {info ? `${info.name} (${info.uf})` : `IBGE ${cd}`}
                    </button>
                  </td>
                  <td>{formatIndicatorValuePt(Number(r[1]), unit)}</td>
                  <td>{formatPctPt(Number(r[2]), true)}</td>
                </tr>
              );
            })}
            {bottom10.map((r, idx) => {
              if (isUf) {
                const uf = String(r[0]);
                const name = String(r[2]);
                const xVal = Number(r[3]);
                const yVal = Number(r[4]);
                return (
                  <tr key={`bot-${uf}`}>
                    <td>{idx + 1}º Menor</td>
                    <td>
                      <button
                        type="button"
                        class="table-link-btn"
                        onClick={() => {
                          selectedUfSignal.value = uf;
                        }}
                      >
                        {name} ({uf})
                      </button>
                    </td>
                    <td>{formatIndicatorValuePt(xVal, unit)}</td>
                    <td>{formatPctPt(yVal, true)}</td>
                  </tr>
                );
              }
              const cd = Number(r[0]);
              const info = directory.get(cd);
              return (
                <tr key={`bot-${cd}`}>
                  <td>{idx + 1}º Menor</td>
                  <td>
                    <button
                      type="button"
                      class="table-link-btn"
                      onClick={() => {
                        selectedIbgeSignal.value = cd;
                      }}
                    >
                      {info ? `${info.name} (${info.uf})` : `IBGE ${cd}`}
                    </button>
                  </td>
                  <td>{formatIndicatorValuePt(Number(r[1]), unit)}</td>
                  <td>{formatPctPt(Number(r[2]), true)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </div>
  );
}
