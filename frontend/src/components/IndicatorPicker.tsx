import { useState } from "preact/hooks";
import { formatPctPt } from "../lib/format";
import {
  activeIndicatorMeta,
  indicatorSignal,
  metaDataSignal,
  selectIndicator,
  yearSignal,
} from "../state/store";
import type { IndicatorMeta, ThemeCode } from "../types/api";

interface SuggestedQuestion {
  code: string;
  label: string;
}

const SUGGESTED_QUESTIONS: readonly SuggestedQuestion[] = [
  { code: "gdp_per_capita", label: "PIB per capita" },
  { code: "household_income_pc", label: "Renda domiciliar per capita" },
  { code: "evangelical_pct", label: "Evangélicos (%)" },
  { code: "fiscal_autonomy_pct", label: "Autonomia fiscal" },
  { code: "illiteracy_rate", label: "Taxa de analfabetismo" },
  { code: "sanitation_sewage_pct", label: "Rede de esgoto (%)" },
];

export function IndicatorPicker() {
  const meta = metaDataSignal.value;
  const rawIndicators = meta?.indicators ?? [];
  const loadedOnly = rawIndicators.filter(
    (ind) => ind.coverage > 0 && ind.ref_year !== null,
  );
  const indicators = loadedOnly.length > 0 ? loadedOnly : rawIndicators;
  const selectedCode = indicatorSignal.value;
  const currentInd = activeIndicatorMeta.value;
  const electionYear = yearSignal.value;

  const themesMap = new Map<ThemeCode, { label: string; items: IndicatorMeta[] }>();
  for (const ind of indicators) {
    const existing = themesMap.get(ind.theme);
    if (existing) {
      existing.items.push(ind);
    } else {
      themesMap.set(ind.theme, { label: ind.theme_label, items: [ind] });
    }
  }

  const themeKeys = Array.from(themesMap.keys());
  const [activeTheme, setActiveTheme] = useState<ThemeCode>(
    currentInd?.theme ?? themeKeys[0] ?? "economy",
  );

  const effectiveTheme = themesMap.has(activeTheme)
    ? activeTheme
    : (themeKeys[0] ?? "economy");
  const visibleIndicators = themesMap.get(effectiveTheme)?.items ?? [];

  const availableSuggestions = SUGGESTED_QUESTIONS.filter((sq) =>
    indicators.some((i) => i.code === sq.code),
  );

  return (
    <div class="panel-section" aria-label="Seleção de indicador socioeconômico ou fiscal">
      <div class="section-header-row">
        <h2 class="section-title">Cruzar votação com indicador municipal</h2>
        {selectedCode && (
          <button
            type="button"
            class="theme-tab-btn"
            onClick={() => selectIndicator(null)}
          >
            Limpar indicador
          </button>
        )}
      </div>

      {availableSuggestions.length > 0 && (
        <div class="question-chips" role="group" aria-label="Perguntas sugeridas">
          {availableSuggestions.map((sq) => (
            <button
              key={sq.code}
              type="button"
              class={`question-chip ${selectedCode === sq.code ? "is-active" : ""}`}
              onClick={() => selectIndicator(sq.code)}
            >
              {sq.label}
            </button>
          ))}
        </div>
      )}

      {themeKeys.length > 0 && (
        <div class="theme-tabs" role="tablist" aria-label="Temas de indicadores">
          {themeKeys.map((themeKey) => {
            const group = themesMap.get(themeKey);
            const isTabActive = effectiveTheme === themeKey;
            return (
              <button
                key={themeKey}
                type="button"
                role="tab"
                aria-selected={isTabActive}
                class={`theme-tab-btn ${isTabActive ? "is-active" : ""}`}
                onClick={() => setActiveTheme(themeKey)}
              >
                {group?.label ?? themeKey}
              </button>
            );
          })}
        </div>
      )}

      <div class="indicator-list" role="listbox" aria-label="Indicadores do tema selecionado">
        {visibleIndicators.map((ind) => {
          const isSelected = selectedCode === ind.code;
          const isOldData =
            ind.ref_year !== null && ind.ref_year <= electionYear - 4;
          return (
            <button
              key={ind.code}
              type="button"
              role="option"
              aria-selected={isSelected}
              class={`indicator-row-btn ${isSelected ? "is-selected" : ""}`}
              onClick={() => selectIndicator(ind.code)}
            >
              <div>
                <div class="indicator-row-title">{ind.label}</div>
                <div class="indicator-row-meta tabular-nums">
                  {ind.unit} · ref. {ind.ref_year ?? "—"} · {ind.source_name} (
                  {formatPctPt(ind.coverage, true, 0)} cob.)
                </div>
              </div>
              {isOldData && (
                <span class="caveat-pill tabular-nums">
                  dado antigo ({ind.ref_year})
                </span>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}
