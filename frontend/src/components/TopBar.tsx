import { useEffect, useRef, useState } from "preact/hooks";
import { OFFICE_LABELS_PT } from "../lib/format";
import { apiClient } from "../services/apiClient";
import {
  canSelectRound2,
  geoLevelSignal,
  isMethodologyOpenSignal,
  mapBoundsTargetSignal,
  metaDataSignal,
  officeSignal,
  registerMunicipalitiesInDirectory,
  roundSignal,
  selectOffice,
  selectedIbgeSignal,
  setGeoLevel,
  themeSignal,
  ufFilterSignal,
  yearSignal,
} from "../state/store";
import type { MunicipalitySearchItem, OfficeCode } from "../types/api";

const DISPLAY_OFFICES: OfficeCode[] = [
  "president",
  "governor",
  "senator",
  "federal_deputy",
  "state_or_district_deputy",
];

const BRAZIL_DEFAULT_BBOX: [number, number, number, number] = [
  -73.99, -33.75, -34.79, 5.27,
];

export function TopBar() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<MunicipalitySearchItem[]>([]);
  const [isOpen, setIsOpen] = useState(false);
  const [highlightedIdx, setHighlightedIdx] = useState(-1);
  const debounceRef = useRef<number | null>(null);

  const meta = metaDataSignal.value;
  const ufs = meta?.ufs ?? [];
  const allowRound2 = canSelectRound2.value;

  useEffect(() => {
    const trimmed = query.trim();
    if (trimmed.length < 2) {
      setResults([]);
      setIsOpen(false);
      setHighlightedIdx(-1);
      return;
    }

    if (debounceRef.current !== null) {
      window.clearTimeout(debounceRef.current);
    }

    debounceRef.current = window.setTimeout(async () => {
      try {
        const res = await apiClient.searchMunicipalities(trimmed, 10);
        setResults(res.items);
        registerMunicipalitiesInDirectory(res.items);
        setIsOpen(res.items.length > 0);
        setHighlightedIdx(res.items.length > 0 ? 0 : -1);
      } catch {
        // Ignore aborted or transient search errors
      }
    }, 180);

    return () => {
      if (debounceRef.current !== null) {
        window.clearTimeout(debounceRef.current);
      }
    };
  }, [query]);

  const handleSelectMunicipality = (item: MunicipalitySearchItem): void => {
    registerMunicipalitiesInDirectory([item]);
    selectedIbgeSignal.value = item.cd_ibge;
    setGeoLevel("municipality");
    if (item.bbox && item.bbox.length === 4) {
      mapBoundsTargetSignal.value = [
        item.bbox[0] ?? -73.99,
        item.bbox[1] ?? -33.75,
        item.bbox[2] ?? -34.79,
        item.bbox[3] ?? 5.27,
      ];
    }
    setQuery(`${item.name} (${item.uf})`);
    setIsOpen(false);
  };

  const handleSearchKeyDown = (e: KeyboardEvent): void => {
    if (!isOpen || results.length === 0) {
      if (e.key === "Escape") {
        setIsOpen(false);
      }
      return;
    }
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setHighlightedIdx((prev) => (prev + 1) % results.length);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setHighlightedIdx((prev) => (prev - 1 + results.length) % results.length);
    } else if (e.key === "Enter") {
      e.preventDefault();
      const chosen = results[highlightedIdx];
      if (chosen) {
        handleSelectMunicipality(chosen);
      }
    } else if (e.key === "Escape") {
      e.preventDefault();
      setIsOpen(false);
    }
  };

  const handleUfChange = (nextUf: string): void => {
    const clean = nextUf.trim().toUpperCase() || null;
    ufFilterSignal.value = clean;
    if (!clean) {
      mapBoundsTargetSignal.value = BRAZIL_DEFAULT_BBOX;
      return;
    }
    const foundUf = ufs.find((u) => u.uf === clean);
    if (foundUf?.bbox) {
      mapBoundsTargetSignal.value = foundUf.bbox;
    }
  };

  const toggleTheme = (): void => {
    const next = themeSignal.value === "light" ? "dark" : "light";
    themeSignal.value = next;
    document.documentElement.setAttribute("data-theme", next);
  };

  return (
    <header class="topbar" role="banner">
      <div class="topbar-brand">
        <h1 class="topbar-title">Território Eleitoral</h1>
        <span class="topbar-edition-badge tabular-nums">
          Eleição {yearSignal.value}
        </span>
      </div>

      <div class="topbar-controls" role="toolbar" aria-label="Filtros eleitorais e territoriais">
        <label class="control-group">
          <span class="control-label">Cargo:</span>
          <select
            class="control-select"
            aria-label="Selecionar cargo eleitoral"
            value={officeSignal.value}
            onChange={(e) =>
              selectOffice((e.currentTarget as HTMLSelectElement).value as OfficeCode)
            }
          >
            {DISPLAY_OFFICES.map((off) => (
              <option key={off} value={off}>
                {OFFICE_LABELS_PT[off]}
              </option>
            ))}
          </select>
        </label>

        <div class="segmented-control" role="group" aria-label="Turno da eleição">
          <button
            type="button"
            class={`segmented-btn tabular-nums ${roundSignal.value === 1 ? "is-active" : ""}`}
            aria-pressed={roundSignal.value === 1}
            onClick={() => {
              roundSignal.value = 1;
            }}
          >
            1º Turno
          </button>
          <button
            type="button"
            class={`segmented-btn tabular-nums ${roundSignal.value === 2 ? "is-active" : ""}`}
            aria-pressed={roundSignal.value === 2}
            disabled={!allowRound2}
            title={
              allowRound2
                ? "Alternar para o 2º turno"
                : "Este cargo é decidido em turno único"
            }
            onClick={() => {
              if (allowRound2) {
                roundSignal.value = 2;
              }
            }}
          >
            2º Turno
          </button>
        </div>

        <div class="segmented-control" role="group" aria-label="Nível de análise territorial">
          <button
            type="button"
            class={`segmented-btn ${geoLevelSignal.value === "state" ? "is-active" : ""}`}
            aria-pressed={geoLevelSignal.value === "state"}
            title="Visão macro consolidada por Estado (27 UFs)"
            onClick={() => {
              setGeoLevel("state");
            }}
          >
            Macro (Estado)
          </button>
          <button
            type="button"
            class={`segmented-btn ${geoLevelSignal.value === "municipality" ? "is-active" : ""}`}
            aria-pressed={geoLevelSignal.value === "municipality"}
            title="Visão micro detalhada por município (5.571 municípios)"
            onClick={() => {
              setGeoLevel("municipality");
            }}
          >
            Micro (Município)
          </button>
        </div>

        <label class="control-group">
          <span class="control-label">Recorte:</span>
          <select
            class="control-select tabular-nums"
            aria-label="Filtrar por Unidade da Federação"
            value={ufFilterSignal.value ?? ""}
            onChange={(e) =>
              handleUfChange((e.currentTarget as HTMLSelectElement).value)
            }
          >
            <option value="">
              {geoLevelSignal.value === "state"
                ? "Brasil (27 UFs)"
                : "Brasil (5.571 mun.)"}
            </option>
            {ufs.map((u) => (
              <option key={u.uf} value={u.uf}>
                {u.uf} — {u.name}
              </option>
            ))}
          </select>
        </label>

        <div class="search-combobox">
          <input
            type="search"
            role="combobox"
            aria-expanded={isOpen}
            aria-autocomplete="list"
            aria-controls="mun-search-listbox"
            aria-activedescendant={
              isOpen && highlightedIdx >= 0 && results[highlightedIdx]
                ? `mun-opt-${results[highlightedIdx]?.cd_ibge}`
                : undefined
            }
            aria-label="Buscar município pelo nome"
            class="search-input"
            placeholder="Buscar município..."
            value={query}
            onInput={(e) => setQuery((e.currentTarget as HTMLInputElement).value)}
            onKeyDown={handleSearchKeyDown}
            onFocus={() => {
              if (results.length > 0) {
                setIsOpen(true);
              }
            }}
            onBlur={() => {
              window.setTimeout(() => setIsOpen(false), 150);
            }}
          />
          {isOpen && results.length > 0 && (
            <ul
              id="mun-search-listbox"
              role="listbox"
              class="search-listbox"
              aria-label="Sugestões de municípios"
            >
              {results.map((item, idx) => (
                <li
                  key={item.cd_ibge}
                  id={`mun-opt-${item.cd_ibge}`}
                  role="option"
                  aria-selected={idx === highlightedIdx}
                  class={`search-option ${idx === highlightedIdx ? "is-highlighted" : ""}`}
                  onMouseDown={(e) => {
                    e.preventDefault();
                    handleSelectMunicipality(item);
                  }}
                >
                  <span>{item.name}</span>
                  <span class="search-option-uf">{item.uf}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      <div class="topbar-actions">
        <button
          type="button"
          class="icon-btn"
          onClick={() => {
            isMethodologyOpenSignal.value = true;
          }}
        >
          Metodologia
        </button>
        <button
          type="button"
          class="icon-btn"
          aria-label={
            themeSignal.value === "light"
              ? "Ativar tema escuro"
              : "Ativar tema claro"
          }
          onClick={toggleTheme}
        >
          {themeSignal.value === "light" ? "Tema Escuro" : "Tema Claro"}
        </button>
      </div>
    </header>
  );
}
