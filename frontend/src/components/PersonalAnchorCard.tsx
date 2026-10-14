import { useEffect, useRef, useState } from "preact/hooks";
import {
  BLOC_LABELS_PT,
  formatIndicatorValuePt,
  formatPctPt,
  formatPpDiffPt,
} from "../lib/format";
import { apiClient } from "../services/apiClient";
import {
  activeDecileSignal,
  activeIndicatorMeta,
  analysisDataSignal,
  anchoredMunicipalitySignal,
  blocSignal,
  electionByIbgeMap,
  indicatorValueByIbgeMap,
  mapBoundsTargetSignal,
  municipalityDirectorySignal,
  registerMunicipalitiesInDirectory,
  selectedIbgeSignal,
} from "../state/store";
import type { DecilePayload, MunicipalitySearchItem } from "../types/api";

export function PersonalAnchorCard() {
  const analysis = analysisDataSignal.value;
  const indMeta = activeIndicatorMeta.value;
  const bloc = blocSignal.value;
  const directory = municipalityDirectorySignal.value;
  const electionMap = electionByIbgeMap.value;
  const indicatorMap = indicatorValueByIbgeMap.value;

  const currentIbge =
    anchoredMunicipalitySignal.value ?? selectedIbgeSignal.value;

  const [query, setQuery] = useState("");
  const [results, setResults] = useState<MunicipalitySearchItem[]>([]);
  const [isOpen, setIsOpen] = useState(false);
  const debounceRef = useRef<number | null>(null);

  useEffect(() => {
    const trimmed = query.trim();
    if (trimmed.length < 2) {
      setResults([]);
      setIsOpen(false);
      return;
    }
    if (debounceRef.current !== null) {
      window.clearTimeout(debounceRef.current);
    }
    debounceRef.current = window.setTimeout(async () => {
      try {
        const res = await apiClient.searchMunicipalities(trimmed, 5);
        setResults(res.items);
        registerMunicipalitiesInDirectory(res.items);
        setIsOpen(res.items.length > 0);
      } catch {
        // Ignore aborted search errors
      }
    }, 180);

    return () => {
      if (debounceRef.current !== null) {
        window.clearTimeout(debounceRef.current);
      }
    };
  }, [query]);

  if (!indMeta || !analysis) {
    return null;
  }

  const handleSelectMunicipality = (item: MunicipalitySearchItem): void => {
    registerMunicipalitiesInDirectory([item]);
    anchoredMunicipalitySignal.value = item.cd_ibge;
    selectedIbgeSignal.value = item.cd_ibge;
    if (item.bbox && item.bbox.length === 4) {
      mapBoundsTargetSignal.value = [
        item.bbox[0] ?? -73.99,
        item.bbox[1] ?? -33.75,
        item.bbox[2] ?? -34.79,
        item.bbox[3] ?? 5.27,
      ];
    }
    setQuery("");
    setIsOpen(false);
  };

  const munInfo = currentIbge !== null ? directory.get(currentIbge) : null;
  const indVal = currentIbge !== null ? indicatorMap.get(currentIbge) : null;
  const elecInfo = currentIbge !== null ? electionMap.get(currentIbge) : null;

  // Find corresponding decile from analysis
  let matchingDecile: DecilePayload | null = null;
  if (typeof indVal === "number" && analysis.deciles.length > 0) {
    for (const d of analysis.deciles) {
      if (indVal >= d.indicator_min && indVal <= d.indicator_max) {
        matchingDecile = d;
        break;
      }
    }
    // Fallback if boundary rounding
    if (!matchingDecile && analysis.deciles.length > 0) {
      const first = analysis.deciles[0];
      const last = analysis.deciles[analysis.deciles.length - 1];
      if (first && indVal <= first.indicator_min) {
        matchingDecile = first;
      } else if (last) {
        matchingDecile = last;
      }
    }
  }

  const cityShare =
    elecInfo
      ? bloc === "left"
        ? elecInfo.leftShare
        : bloc === "center"
          ? elecInfo.centerShare
          : elecInfo.rightShare
      : null;

  const decileShare = matchingDecile ? matchingDecile.weighted_share : null;
  const diffFromPeers =
    cityShare !== null && decileShare !== null
      ? (cityShare - decileShare) * 100
      : null;

  const blocLabel = BLOC_LABELS_PT[bloc];

  return (
    <article
      class="personal-anchor-card"
      aria-label="Posicionamento do seu município no indicador"
    >
      <header class="personal-anchor-header">
        <span class="personal-anchor-badge">📍 Seu Município na História</span>
        <h3 class="personal-anchor-title">
          {munInfo
            ? `${munInfo.name} (${munInfo.uf})`
            : "Como a sua cidade se posiciona?"}
        </h3>
      </header>

      {/* Seção de Busca / Troca de Cidade */}
      <div class="personal-anchor-search-wrap">
        <label class="sr-only" htmlFor="anchor-city-search">
          Buscar cidade
        </label>
        <input
          id="anchor-city-search"
          type="search"
          class="personal-anchor-input"
          placeholder="Digite o nome da sua cidade..."
          value={query}
          onInput={(e) => setQuery((e.target as HTMLInputElement).value)}
        />

        {isOpen && results.length > 0 && (
          <ul class="personal-anchor-results" role="listbox">
            {results.map((item) => (
              <li
                key={item.cd_ibge}
                role="option"
                aria-selected={false}
                class="personal-anchor-result-item"
                onClick={() => handleSelectMunicipality(item)}
              >
                <strong>{item.name}</strong> — {item.uf} ({item.region})
              </li>
            ))}
          </ul>
        )}
      </div>

      {munInfo && (
        <div class="personal-anchor-body">
          <div class="personal-anchor-stats-row">
            <div class="personal-stat-cell">
              <span class="personal-stat-label">{indMeta.label}:</span>
              <span class="personal-stat-val tabular-nums">
                {indVal !== null && indVal !== undefined
                  ? formatIndicatorValuePt(indVal, indMeta.unit)
                  : "Sem dado"}
              </span>
              {matchingDecile && (
                <span class="personal-stat-sub">
                  {matchingDecile.decile}º decil (D{matchingDecile.decile})
                </span>
              )}
            </div>

            <div class="personal-stat-cell">
              <span class="personal-stat-label">
                Voto em {blocLabel}:
              </span>
              <span class="personal-stat-val tabular-nums">
                {cityShare !== null ? formatPctPt(cityShare, true) : "—"}
              </span>
              <span class="personal-stat-sub">votos válidos locais</span>
            </div>

            {decileShare !== null && (
              <div class="personal-stat-cell">
                <span class="personal-stat-label">
                  Média de cidades similares:
                </span>
                <span class="personal-stat-val tabular-nums">
                  {formatPctPt(decileShare, true)}
                </span>
                <span class="personal-stat-sub">
                  D{matchingDecile?.decile} ({indMeta.label})
                </span>
              </div>
            )}
          </div>

          {diffFromPeers !== null && matchingDecile && (
            <div class="personal-anchor-insight">
              <p>
                Em <strong>{munInfo.name}</strong>, o bloco de{" "}
                <strong>{blocLabel}</strong> obteve{" "}
                <strong>{formatPctPt(cityShare ?? 0, true)}</strong>, contra uma
                média de{" "}
                <strong>{formatPctPt(decileShare ?? 0, true)}</strong> em
                municípios de perfil socioeconômico similar (Decil D
                {matchingDecile.decile}) — saldo de{" "}
                <strong>{formatPpDiffPt(diffFromPeers, false)}</strong> frente a
                seus pares.
              </p>
            </div>
          )}

          <div class="personal-anchor-actions">
            {matchingDecile && (
              <button
                type="button"
                class="theme-tab-btn"
                onClick={() => {
                  activeDecileSignal.value = matchingDecile.decile;
                }}
              >
                Destacar cidades similares (D{matchingDecile.decile}) no mapa
              </button>
            )}
            <button
              type="button"
              class="theme-tab-btn"
              onClick={() => {
                selectedIbgeSignal.value = munInfo.cd_ibge;
              }}
            >
              Ver ficha completa
            </button>
            <button
              type="button"
              class="theme-tab-btn"
              onClick={() => {
                anchoredMunicipalitySignal.value = null;
              }}
            >
              Trocar cidade
            </button>
          </div>
        </div>
      )}
    </article>
  );
}
