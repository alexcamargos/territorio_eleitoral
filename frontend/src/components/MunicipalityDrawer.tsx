import { useEffect, useState } from "preact/hooks";
import {
  BLOC_LABELS_PT,
  OFFICE_LABELS_PT,
  formatDecimalPt,
  formatIndicatorValuePt,
  formatIntegerPt,
  formatPctPt,
} from "../lib/format";
import { apiClient } from "../services/apiClient";
import {
  officeSignal,
  registerMunicipalitiesInDirectory,
  roundSignal,
  selectIndicator,
  selectedIbgeSignal,
  yearSignal,
} from "../state/store";
import type { MunicipalityProfileResponse, OfficeCode } from "../types/api";

export function MunicipalityDrawer() {
  const cdIbge = selectedIbgeSignal.value;
  const year = yearSignal.value;
  const round = roundSignal.value;
  const activeOffice = officeSignal.value;

  const [profile, setProfile] = useState<MunicipalityProfileResponse | null>(
    null,
  );
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (cdIbge === null) {
      setProfile(null);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setError(null);

    apiClient
      .fetchMunicipalityProfile(cdIbge, year, round)
      .then((res) => {
        if (!cancelled) {
          setProfile(res);
          registerMunicipalitiesInDirectory([
            {
              cd_ibge: res.municipality.cd_ibge,
              name: res.municipality.name,
              uf: res.municipality.uf,
              region: res.municipality.region,
            },
          ]);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(
            err instanceof Error
              ? err.message
              : "Não foi possível carregar a ficha do município.",
          );
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [cdIbge, year, round]);

  useEffect(() => {
    if (cdIbge === null) {
      return;
    }
    const handleKey = (e: KeyboardEvent): void => {
      if (e.key === "Escape") {
        selectedIbgeSignal.value = null;
      }
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [cdIbge]);

  if (cdIbge === null) {
    return null;
  }

  const closeDrawer = (): void => {
    selectedIbgeSignal.value = null;
  };

  const resolvedOfficeKey =
    activeOffice === "state_or_district_deputy"
      ? profile?.elections["state_deputy"]
        ? "state_deputy"
        : "district_deputy"
      : activeOffice;
  const currentOfficeResult =
    profile?.elections[resolvedOfficeKey] ??
    profile?.elections["president"];

  return (
    <div
      class="drawer-backdrop"
      onClick={(e) => {
        if (e.target === e.currentTarget) {
          closeDrawer();
        }
      }}
    >
      <aside
        class="municipality-drawer"
        role="dialog"
        aria-modal="true"
        aria-label="Ficha detalhada do município"
      >
        <header class="drawer-header">
          <div>
            <h2 class="editorial-headline">
              {profile
                ? `${profile.municipality.name} — ${profile.municipality.uf}`
                : `Município ${cdIbge}`}
            </h2>
            {profile && (
              <div class="indicator-row-meta tabular-nums">
                Código IBGE:{" "}
                <span class="mono-code">{profile.municipality.cd_ibge}</span> ·{" "}
                {profile.municipality.region} ·{" "}
                {formatDecimalPt(profile.municipality.area_km2, 1)} km²
                {profile.municipality.is_capital ? " · Capital Estadual" : ""}
              </div>
            )}
          </div>
          <button
            type="button"
            class="icon-btn"
            aria-label="Fechar ficha municipal"
            onClick={closeDrawer}
          >
            Fechar ✕
          </button>
        </header>

        <div class="drawer-body">
          {loading && <p>Carregando dados oficiais do município…</p>}
          {error && <p class="caveat-pill">{error}</p>}

          {profile && currentOfficeResult && (
            <section class="panel-section">
              <div class="section-header-row">
                <h3 class="section-title">
                  Resultado Eleitoral —{" "}
                  {OFFICE_LABELS_PT[resolvedOfficeKey as OfficeCode] ??
                    resolvedOfficeKey}{" "}
                  ({year}, {round}º turno)
                </h3>
              </div>

              <div class="bloc-bar-tri" style={{ height: "12px" }}>
                <div
                  class="bloc-seg-left"
                  style={{
                    width: `${(currentOfficeResult.bloc_shares.left * 100).toFixed(1)}%`,
                  }}
                />
                <div
                  class="bloc-seg-center"
                  style={{
                    width: `${(currentOfficeResult.bloc_shares.center * 100).toFixed(1)}%`,
                  }}
                />
                <div
                  class="bloc-seg-right"
                  style={{
                    width: `${(currentOfficeResult.bloc_shares.right * 100).toFixed(1)}%`,
                  }}
                />
              </div>

              <div class="bloc-labels-row tabular-nums">
                <span>
                  Esquerda:{" "}
                  <strong>
                    {formatPctPt(currentOfficeResult.bloc_shares.left, true)}
                  </strong>
                </span>
                <span>
                  Centro:{" "}
                  <strong>
                    {formatPctPt(currentOfficeResult.bloc_shares.center, true)}
                  </strong>
                </span>
                <span>
                  Direita:{" "}
                  <strong>
                    {formatPctPt(currentOfficeResult.bloc_shares.right, true)}
                  </strong>
                </span>
              </div>

              <div class="indicator-row-meta tabular-nums">
                Eleitores aptos:{" "}
                <strong>
                  {formatIntegerPt(currentOfficeResult.turnout.eligible)}
                </strong>{" "}
                · Comparecimento:{" "}
                <strong>
                  {formatPctPt(currentOfficeResult.turnout.turnout_pct, false)}
                </strong>{" "}
                · Votos válidos:{" "}
                <strong>
                  {formatIntegerPt(currentOfficeResult.turnout.valid)}
                </strong>{" "}
                · Brancos/Nulos:{" "}
                <strong>
                  {formatPctPt(
                    currentOfficeResult.turnout.blank_null_pct,
                    false,
                  )}
                </strong>
              </div>

              {currentOfficeResult.top_candidates.length > 0 && (
                <table
                  class="accessible-table tabular-nums"
                  aria-label="Candidatos mais votados no município"
                >
                  <thead>
                    <tr>
                      <th scope="col">Candidato</th>
                      <th scope="col">Partido / Bloco</th>
                      <th scope="col">Votos</th>
                      <th scope="col">% Válidos</th>
                    </tr>
                  </thead>
                  <tbody>
                    {currentOfficeResult.top_candidates.map((cand) => (
                      <tr key={`${cand.ballot_name}-${cand.party_code}`}>
                        <td>
                          <strong>{cand.ballot_name}</strong>
                        </td>
                        <td>
                          {cand.party_code} ({BLOC_LABELS_PT[cand.bloc]})
                        </td>
                        <td>{formatIntegerPt(cand.votes)}</td>
                        <td>{formatPctPt(cand.share, true)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </section>
          )}

          {profile && (
            <section class="panel-section">
              <div class="section-header-row">
                <h3 class="section-title">
                  Indicadores Socioeconômicos e Fiscais ({profile.indicators.length})
                </h3>
              </div>
              <table
                class="accessible-table tabular-nums"
                aria-label="Indicadores municipais e percentil nacional"
              >
                <thead>
                  <tr>
                    <th scope="col">Indicador</th>
                    <th scope="col">Valor</th>
                    <th scope="col">Ano</th>
                    <th scope="col">Percentil Nac.</th>
                  </tr>
                </thead>
                <tbody>
                  {profile.indicators.map((ind) => (
                    <tr key={ind.code}>
                      <td>
                        <button
                          type="button"
                          class="table-link-btn"
                          title="Cruzar este indicador no mapa"
                          onClick={() => {
                            selectIndicator(ind.code);
                            closeDrawer();
                          }}
                        >
                          {ind.label}
                        </button>
                      </td>
                      <td>
                        <strong>
                          {formatIndicatorValuePt(ind.value, ind.unit)}
                        </strong>
                      </td>
                      <td>{ind.ref_year}</td>
                      <td>
                        {ind.national_percentile !== null
                          ? `P${formatDecimalPt(ind.national_percentile, 0)}`
                          : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>
          )}
        </div>
      </aside>
    </div>
  );
}
