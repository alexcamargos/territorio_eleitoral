import { useEffect } from "preact/hooks";
import { AccessibleDataTable } from "./components/AccessibleDataTable";
import { DecileBarChart } from "./components/DecileBarChart";
import { ExtremesContrastCard } from "./components/ExtremesContrastCard";
import { IndicatorPicker } from "./components/IndicatorPicker";
import { InsightCards } from "./components/InsightCards";
import { MapCanvas } from "./components/MapCanvas";
import { MapTooltip } from "./components/MapTooltip";
import { MethodologyModal } from "./components/MethodologyModal";
import { MunicipalityDrawer } from "./components/MunicipalityDrawer";
import { PersonalAnchorCard } from "./components/PersonalAnchorCard";
import { ScatterPlot } from "./components/ScatterPlot";
import { StoryStepper } from "./components/StoryStepper";
import { StoryTracksBar } from "./components/StoryTracksBar";
import { TopBar } from "./components/TopBar";
import {
  BLOC_LABELS_PT,
  OFFICE_LABELS_PT,
  formatIntegerPt,
  formatPctPt,
} from "./lib/format";
import { ApiClientError, apiClient } from "./services/apiClient";
import {
  activeDecileSignal,
  activeIndicatorMeta,
  analysisDataSignal,
  analysisUfDataSignal,
  apiErrorSignal,
  blocSignal,
  electionMapDataSignal,
  electionUfMapDataSignal,
  geoLevelSignal,
  indicatorMapDataSignal,
  indicatorUfMapDataSignal,
  indicatorSignal,
  isLoadingAnalysisSignal,
  isLoadingMapSignal,
  isMethodologyOpenSignal,
  mapLayerModeSignal,
  metaDataSignal,
  navigateToStoryStep,
  officeSignal,
  roundSignal,
  storyStepSignal,
  ufFilterSignal,
  viewModeTableSignal,
  yearSignal,
} from "./state/store";
import { initUrlSynchronization } from "./state/urlSync";
import type { BlocCode, InsightCardPayload } from "./types/api";

const BLOC_ORDER: readonly BlocCode[] = ["left", "center", "right"];

export function App() {
  useEffect(() => {
    const cleanupUrl = initUrlSynchronization();
    apiClient
      .fetchMeta()
      .then((meta) => {
        metaDataSignal.value = meta;
      })
      .catch((err: unknown) => {
        if (err instanceof Error && err.name === "AbortError") {
          return;
        }
        apiErrorSignal.value =
          err instanceof Error
            ? err.message
            : "Falha ao carregar metadados iniciais.";
      });
    return cleanupUrl;
  }, []);

  // Load electoral map data whenever year, office, round, uf, or geoLevel changes
  useEffect(() => {
    const year = yearSignal.value;
    const office = officeSignal.value;
    const round = roundSignal.value;
    const uf = ufFilterSignal.value;
    const level = geoLevelSignal.value;

    isLoadingMapSignal.value = true;
    apiErrorSignal.value = null;

    apiClient
      .fetchElectionMap(year, office, round, uf, level)
      .then((res) => {
        if (level === "state") {
          electionUfMapDataSignal.value = res;
        } else {
          electionMapDataSignal.value = res;
        }
      })
      .catch((err: unknown) => {
        if (err instanceof Error && err.name === "AbortError") {
          return;
        }
        if (err instanceof ApiClientError) {
          apiErrorSignal.value = err.message;
        }
      })
      .finally(() => {
        isLoadingMapSignal.value = false;
      });
  }, [
    yearSignal.value,
    officeSignal.value,
    roundSignal.value,
    ufFilterSignal.value,
    geoLevelSignal.value,
  ]);

  // Load indicator map data whenever indicator, uf, or geoLevel changes
  useEffect(() => {
    const code = indicatorSignal.value;
    const uf = ufFilterSignal.value;
    const level = geoLevelSignal.value;
    if (!code) {
      indicatorMapDataSignal.value = null;
      indicatorUfMapDataSignal.value = null;
      return;
    }

    apiClient
      .fetchIndicatorMap(code, uf, null, level)
      .then((res) => {
        if (level === "state") {
          indicatorUfMapDataSignal.value = res;
        } else {
          indicatorMapDataSignal.value = res;
        }
      })
      .catch((err: unknown) => {
        if (err instanceof Error && err.name === "AbortError") {
          return;
        }
        if (err instanceof ApiClientError) {
          apiErrorSignal.value = err.message;
        }
      });
  }, [indicatorSignal.value, ufFilterSignal.value, geoLevelSignal.value]);

  // Load unified bivariate analysis whenever indicator, election, bloc, uf, or geoLevel changes
  useEffect(() => {
    const code = indicatorSignal.value;
    const level = geoLevelSignal.value;
    if (!code) {
      analysisDataSignal.value = null;
      analysisUfDataSignal.value = null;
      return;
    }

    isLoadingAnalysisSignal.value = true;
    apiClient
      .fetchAnalysis({
        year: yearSignal.value,
        office: officeSignal.value,
        round: roundSignal.value,
        indicator: code,
        bloc: blocSignal.value,
        uf: ufFilterSignal.value,
        level,
      })
      .then((res) => {
        if (level === "state") {
          analysisUfDataSignal.value = res;
        }
        analysisDataSignal.value = res;
      })
      .catch((err: unknown) => {
        if (err instanceof Error && err.name === "AbortError") {
          return;
        }
        if (err instanceof ApiClientError) {
          apiErrorSignal.value = err.message;
        }
      })
      .finally(() => {
        isLoadingAnalysisSignal.value = false;
      });
  }, [
    yearSignal.value,
    officeSignal.value,
    roundSignal.value,
    indicatorSignal.value,
    blocSignal.value,
    ufFilterSignal.value,
    geoLevelSignal.value,
  ]);

  const isMacro = geoLevelSignal.value === "state";
  const electionMap = isMacro
    ? (electionUfMapDataSignal.value ?? electionMapDataSignal.value)
    : electionMapDataSignal.value;
  const summary = electionMap?.national_summary;
  const activeInd = activeIndicatorMeta.value;
  const analysis = analysisDataSignal.value;
  const bloc = blocSignal.value;
  const step = storyStepSignal.value;

  // Deterministic Stage 1 macro headline card from backend `national_summary`
  const macroCards: InsightCardPayload[] = [];
  if (summary && electionMap) {
    let leadingBloc: BlocCode = "right";
    if (
      summary.bloc_shares.left >= summary.bloc_shares.right &&
      summary.bloc_shares.left >= summary.bloc_shares.center
    ) {
      leadingBloc = "left";
    } else if (
      summary.bloc_shares.center > summary.bloc_shares.left &&
      summary.bloc_shares.center > summary.bloc_shares.right
    ) {
      leadingBloc = "center";
    }
    const totalMuns =
      summary.municipalities_won.left +
      summary.municipalities_won.center +
      summary.municipalities_won.right;
    const officeLabel = OFFICE_LABELS_PT[electionMap.election.office];
    const leadLabel = BLOC_LABELS_PT[leadingBloc].toLowerCase();
    const shareFmt = formatPctPt(summary.bloc_shares[leadingBloc], true);
    const wonFmt = formatIntegerPt(summary.municipalities_won[leadingBloc]);
    const totFmt = formatIntegerPt(totalMuns);
    const ufsWon = summary.ufs_won;
    const ufsLeadText =
      isMacro && ufsWon
        ? ` e vencendo em **${ufsWon[leadingBloc]}** das **27** UFs`
        : "";

    macroCards.push({
      template_id: "macro_overview",
      severity: "headline",
      title: isMacro
        ? "Panorama Consolidado por Estados (27 UFs)"
        : "Panorama Nacional por Blocos",
      text: `Em ${electionMap.election.year} (${electionMap.election.round}º turno, ${officeLabel}), o bloco de **${leadLabel}** somou **${shareFmt}** dos votos válidos, liderando em **${wonFmt}** dos **${totFmt}** municípios${ufsLeadText}.`,
      params: {},
    });
    macroCards.push({
      template_id: "ecological_reminder",
      severity: "caveat",
      title: "Interpretação Ecológica",
      text: "Estes resultados descrevem padrões agregados **entre municípios** e não permitem inferir o voto individual de moradores (evitando falácia ecológica).",
      params: {},
    });
  }

  return (
    <>
      <TopBar />

      <main class="workspace-grid">
        <MapCanvas />

        <aside
          class="narrative-panel"
          aria-label="Painel analítico e narrativo"
        >
          <StoryTracksBar />
          <StoryStepper />

          <div class="narrative-scroll">
            {apiErrorSignal.value && (
              <div class="insight-card severity-caveat" role="alert">
                <h3 class="insight-card-title">Aviso do Sistema</h3>
                <p class="insight-card-body">{apiErrorSignal.value}</p>
              </div>
            )}

            {/* Seção 1: Panorama Eleitoral por Blocos */}
            <section class="panel-section">
              <h2 class="editorial-headline">
                {activeInd
                  ? `${activeInd.label} × Voto em ${BLOC_LABELS_PT[bloc]}`
                  : `Distribuição Territorial do Voto (${OFFICE_LABELS_PT[officeSignal.value]})`}
              </h2>

              {summary && (
                <div class="national-summary-box">
                  <div class="bloc-bar-tri" style={{ height: "10px" }}>
                    <div
                      class="bloc-seg-left"
                      style={{
                        width: `${(summary.bloc_shares.left * 100).toFixed(1)}%`,
                      }}
                    />
                    <div
                      class="bloc-seg-center"
                      style={{
                        width: `${(summary.bloc_shares.center * 100).toFixed(1)}%`,
                      }}
                    />
                    <div
                      class="bloc-seg-right"
                      style={{
                        width: `${(summary.bloc_shares.right * 100).toFixed(1)}%`,
                      }}
                    />
                  </div>

                  <div
                    class="national-bloc-grid"
                    role="group"
                    aria-label="Selecionar bloco ideológico em foco"
                  >
                    {BLOC_ORDER.map((b) => {
                      const isSel = bloc === b;
                      const dotColor =
                        b === "left"
                          ? "var(--bloc-left)"
                          : b === "center"
                            ? "var(--bloc-center)"
                            : "var(--bloc-right)";
                      return (
                        <button
                          key={b}
                          type="button"
                          class={`bloc-stat-item tabular-nums ${isSel ? "is-selected" : ""}`}
                          aria-pressed={isSel}
                          onClick={() => {
                            blocSignal.value = b;
                            if (!indicatorSignal.value) {
                              mapLayerModeSignal.value = "electoral_bloc";
                            }
                          }}
                        >
                          <div class="bloc-stat-name">
                            <span
                              class="bloc-dot"
                              style={{ backgroundColor: dotColor }}
                            />
                            {BLOC_LABELS_PT[b]}
                          </div>
                          <div class="bloc-stat-kpi">
                            {formatPctPt(summary.bloc_shares[b], true)}
                          </div>
                          <div class="bloc-stat-sub">
                            {isMacro && summary.ufs_won
                              ? `Líder em ${summary.ufs_won[b]} UFs`
                              : `Líder em ${formatIntegerPt(summary.municipalities_won[b])} mun.`}
                          </div>
                        </button>
                      );
                    })}
                  </div>
                </div>
              )}
            </section>

            {/* Seção 2: Seletor de Indicador (A Pergunta) */}
            <IndicatorPicker />

            {/* Etapa 1 sem indicador selecionado: Panorama + Convite */}
            {!activeInd && macroCards.length > 0 && (
              <section class="panel-section">
                <InsightCards cardsOverride={macroCards} />
                <button
                  type="button"
                  class="icon-btn"
                  style={{ alignSelf: "flex-start" }}
                  onClick={() => navigateToStoryStep(2)}
                >
                  Escolher um indicador acima para cruzar com o voto →
                </button>
              </section>
            )}

            {/* Etapas 3 e 4: Revelação (Contraste, Scatter + Decis) e Conclusão (Insights + Ancoragem) */}
            {activeInd && analysis && (
              <>
                <section class="panel-section">
                  <ExtremesContrastCard />
                </section>

                <section class="panel-section">
                  <div class="section-header-row">
                    <h2 class="section-title">
                      Dispersão e Decis Ponderados (n ={" "}
                      <span class="tabular-nums">
                        {formatIntegerPt(analysis.sample.valid_pairs)}
                      </span>{" "}
                      mun.)
                    </h2>
                    <button
                      type="button"
                      class="theme-tab-btn"
                      aria-pressed={viewModeTableSignal.value}
                      onClick={() => {
                        viewModeTableSignal.value = !viewModeTableSignal.value;
                      }}
                    >
                      {viewModeTableSignal.value
                        ? "Ver como gráfico"
                        : "Ver como tabela"}
                    </button>
                  </div>

                  {viewModeTableSignal.value ? (
                    <AccessibleDataTable />
                  ) : (
                    <>
                      <ScatterPlot />
                      <div style={{ marginTop: "8px" }}>
                        <div class="section-header-row">
                          <span class="indicator-row-meta">
                            Participação do bloco de{" "}
                            <strong>{BLOC_LABELS_PT[bloc]}</strong> do 1º decil
                            (10% menores) ao 10º decil (10% maiores) — passe o
                            mouse para destacar no mapa:
                          </span>
                          {activeDecileSignal.value !== null && (
                            <button
                              type="button"
                              class="theme-tab-btn"
                              onClick={() => {
                                activeDecileSignal.value = null;
                              }}
                            >
                              Limpar destaque D{activeDecileSignal.value}
                            </button>
                          )}
                        </div>
                        <DecileBarChart />
                      </div>
                    </>
                  )}
                </section>

                <section class="panel-section">
                  <div class="section-header-row">
                    <h2 class="section-title">
                      Síntese Determinística (Etapa {step === 4 ? "4" : "3–4"})
                    </h2>
                    {step < 4 && (
                      <button
                        type="button"
                        class="theme-tab-btn"
                        onClick={() => navigateToStoryStep(4)}
                      >
                        Focar Conclusão
                      </button>
                    )}
                  </div>
                  <InsightCards />
                  <PersonalAnchorCard />
                </section>
              </>
            )}
          </div>

          <footer class="narrative-footer">
            <span>
              Análise agregada por <strong>municípios</strong> (nunca
              indivíduos).
            </span>
            <button
              type="button"
              class="theme-tab-btn"
              onClick={() => {
                isMethodologyOpenSignal.value = true;
              }}
            >
              Metodologia, Fontes e Partidos
            </button>
          </footer>
        </aside>
      </main>

      <MapTooltip />
      <MunicipalityDrawer />
      <MethodologyModal />
    </>
  );
}
