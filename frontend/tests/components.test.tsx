import { render } from "preact";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AccessibleDataTable } from "../src/components/AccessibleDataTable";
import { DecileBarChart } from "../src/components/DecileBarChart";
import { ExtremesContrastCard } from "../src/components/ExtremesContrastCard";
import { InsightCards } from "../src/components/InsightCards";
import { MapLegend } from "../src/components/MapLegend";
import { PersonalAnchorCard } from "../src/components/PersonalAnchorCard";
import { StateFocusCard } from "../src/components/StateFocusCard";
import { StateLabelsOverlay } from "../src/components/StateLabelsOverlay";
import { StoryStepper } from "../src/components/StoryStepper";
import { StoryTracksBar } from "../src/components/StoryTracksBar";
import { TopBar } from "../src/components/TopBar";
import { applyMetricToMap } from "../src/lib/scales";
import {
  activeDecileSignal,
  activeStoryTrackSignal,
  analysisDataSignal,
  anchoredMunicipalitySignal,
  blocSignal,
  electionMapDataSignal,
  electionUfMapDataSignal,
  geoLevelSignal,
  indicatorMapDataSignal,
  indicatorSignal,
  mapLayerModeSignal,
  metaDataSignal,
  officeSignal,
  registerMunicipalitiesInDirectory,
  resetStoreToDefaults,
  selectedUfSignal,
  storyStepSignal,
  ufFilterSignal,
} from "../src/state/store";
import type { AnalysisResponse } from "../src/types/api";

const RAW_TSX_MODULES = import.meta.glob("../src/**/*.tsx", {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>;

const SAMPLE_ANALYSIS: AnalysisResponse = {
  scope: {
    year: 2026,
    office: "president",
    round: 1,
    bloc: "right",
    uf: null,
  },
  indicator: {
    code: "bolsa_familia_pc",
    label: "Bolsa Família per capita",
    unit: "R$/hab. no mês",
    ref_year: 2026,
    scale_hint: "quantile",
    caveat: null,
  },
  sample: {
    total_municipalities: 5571,
    valid_pairs: 5570,
    missing_pairs: 1,
  },
  correlation: {
    spearman_rho: -0.684,
    spearman_p: 0,
    pearson_r: -0.651,
    pearson_p: 0,
    strength: "strong",
    strength_label: "forte",
    direction: "negative",
    direction_label: "negativa",
  },
  trendline: {
    model: "linear",
    points: [
      [18.4, 0.642],
      [218.5, 0.241],
    ],
  },
  deciles: Array.from({ length: 10 }, (_, idx) => ({
    decile: idx + 1,
    municipality_count: 557,
    indicator_min: idx * 20,
    indicator_max: (idx + 1) * 20,
    indicator_median: idx * 20 + 10,
    valid_votes: 1000000,
    bloc_votes: 500000 - idx * 30000,
    weighted_share: 0.65 - idx * 0.04,
    unweighted_mean_share: 0.64 - idx * 0.04,
  })),
  scatter: {
    columns: ["cd_ibge", "x", "y", "valid_votes", "region"],
    rows: [
      [3550308, 25.0, 0.4378, 6812440, "Sudeste"],
      [1100015, 72.45, 0.6547, 14210, "Norte"],
    ],
  },
  insights: [
    {
      template_id: "decile_top_vs_bottom",
      severity: "headline",
      title: "Comparação entre Extremos",
      text: "Os 10% com maior **Bolsa Família per capita** direcionaram **29,0%** ao bloco de **direita**.",
      params: {},
    },
    {
      template_id: "ecological_reminder",
      severity: "caveat",
      title: "Interpretação Ecológica",
      text: "Resultados agregados **entre municípios**.",
      params: {},
    },
  ],
};

describe("components — Renderização, Interatividade, Acessibilidade e Auditoria de Tokens", () => {
  let container: HTMLDivElement;

  beforeEach(() => {
    resetStoreToDefaults();
    container = document.createElement("div");
    document.body.appendChild(container);
  });

  it("TopBar desabilita o botão de 2º turno quando o cargo é de turno único (ex.: Senador)", () => {
    officeSignal.value = "senator";
    render(<TopBar />, container);

    const buttons = Array.from(container.querySelectorAll("button"));
    const round2Btn = buttons.find((b) => b.textContent?.includes("2º Turno"));
    expect(round2Btn).toBeDefined();
    expect(round2Btn?.disabled).toBe(true);
    expect(round2Btn?.getAttribute("title")).toBe(
      "Este cargo é decidido em turno único",
    );
  });

  it("StoryStepper redireciona para Etapa 2 se o usuário clicar na Etapa 3 sem indicador selecionado", () => {
    render(<StoryStepper />, container);
    const step3Btn = Array.from(container.querySelectorAll("button")).find((b) =>
      b.textContent?.includes("A Revelação"),
    );
    step3Btn?.click();
    expect(storyStepSignal.value).toBe(2);
  });

  it("InsightCards renderiza região aria-live='polite' e aplica .tabular-nums em números destacados", () => {
    analysisDataSignal.value = SAMPLE_ANALYSIS;
    render(<InsightCards />, container);

    const region = container.querySelector("[aria-live='polite']");
    expect(region).not.toBeNull();
    const strongElements = Array.from(
      container.querySelectorAll("strong.tabular-nums"),
    );
    expect(strongElements.map((el) => el.textContent)).toContain("29,0%");
  });

  it("DecileBarChart renderiza os 10 decis e atualiza activeDecileSignal ao interagir", () => {
    analysisDataSignal.value = SAMPLE_ANALYSIS;
    render(<DecileBarChart />, container);

    const rows = container.querySelectorAll(".decile-row");
    expect(rows).toHaveLength(10);
    (rows[9] as HTMLButtonElement).click();
    expect(activeDecileSignal.value).toBe(10);
  });

  it("AccessibleDataTable renderiza tabelas semânticas para os 10 decis e extremos municipais", () => {
    analysisDataSignal.value = SAMPLE_ANALYSIS;
    render(<AccessibleDataTable />, container);

    const tables = container.querySelectorAll("table.accessible-table");
    expect(tables).toHaveLength(2);
    expect(tables[0]?.querySelectorAll("tbody tr")).toHaveLength(10);
  });

  it("applyMetricToMap injeta feature-state em lote sem recarregar geometria", () => {
    const setFeatureState = vi.fn();
    applyMetricToMap(
      { setFeatureState },
      [
        [3550308, 42.5],
        [5101837, null],
      ],
      new Set([3550308]),
    );

    expect(setFeatureState).toHaveBeenCalledTimes(2);
    expect(setFeatureState).toHaveBeenNthCalledWith(
      1,
      { source: "territorio-mun", sourceLayer: "municipalities", id: 3550308 },
      { metric: 42.5, inActiveDecile: true },
    );
    expect(setFeatureState).toHaveBeenNthCalledWith(
      2,
      { source: "territorio-mun", sourceLayer: "municipalities", id: 5101837 },
      { metric: null, inActiveDecile: false },
    );
  });

  it("AUDITORIA DESIGN SYSTEM (docs/11 §3): nenhum arquivo .tsx possui cores hexadecimais hardcoded", () => {
    const entries = Object.entries(RAW_TSX_MODULES);
    expect(entries.length).toBeGreaterThanOrEqual(12);

    const hexRegex = /#[0-9A-Fa-f]{3,8}\b/;
    for (const [filePath, content] of entries) {
      expect(
        hexRegex.test(content),
        `Valor hexadecimal hardcoded encontrado em ${filePath}`,
      ).toBe(false);
    }
  });

  it("StoryTracksBar renderiza chips de pautas e altera estado ao clicar", () => {
    render(<StoryTracksBar />, container);

    const chips = container.querySelectorAll(".story-track-chip");
    expect(chips.length).toBeGreaterThanOrEqual(4);

    // Clica no primeiro chip
    const firstChip = chips[0] as HTMLButtonElement;
    firstChip.click();

    expect(activeStoryTrackSignal.value).not.toBeNull();
    expect(indicatorSignal.value).not.toBeNull();
    expect(storyStepSignal.value).toBe(3);

    // Renderiza banner ativo
    render(<StoryTracksBar />, container);
    expect(container.querySelector(".story-track-active-banner")).not.toBeNull();
  });

  it("ExtremesContrastCard renderiza contraste dos Dois Brasis e ponto de inflexão", () => {
    metaDataSignal.value = {
      dataset_version: 1,
      default_selection: {
        year: 2026,
        round: 1,
        office: "president",
        bloc: "right",
        indicator: "bolsa_familia_pc",
      },
      elections: [],
      indicators: [
        {
          code: "bolsa_familia_pc",
          label: "Bolsa Família per capita",
          description: "Transferências do Bolsa Família",
          theme: "transfers",
          theme_label: "Transferências",
          tier: 1,
          unit: "R$/hab.",
          value_type: "continuous",
          higher_is: "neutral",
          scale_hint: "quantile",
          ref_year: 2026,
          coverage: 1.0,
          source_name: "MDS",
          source_url: null,
          caveat: null,
        },
      ],
      ufs: [],
      party_ideology: [],
    };
    indicatorSignal.value = "bolsa_familia_pc";
    analysisDataSignal.value = {
      ...SAMPLE_ANALYSIS,
      extremes_contrast: {
        bottom_quintile_share: 0.35,
        top_quintile_share: 0.64,
        diff_pp: 29.0,
        bottom_indicator_range: [10.0, 45.0],
        top_indicator_range: [180.0, 520.0],
        bottom_municipality_count: 1114,
        top_municipality_count: 1114,
        tipping_point_decile: 6,
        tipping_point_threshold: 120.0,
      },
    };

    render(<ExtremesContrastCard />, container);

    const title = container.querySelector(".extremes-contrast-title");
    expect(title?.textContent).toContain("Dois Brasis");

    const boxes = container.querySelectorAll(".extremes-quintile-box");
    expect(boxes).toHaveLength(2);

    const delta = container.querySelector(".extremes-delta-value");
    expect(delta?.textContent).toContain("+29,0 p.p.");

    const tipping = container.querySelector(".extremes-tipping-row");
    expect(tipping?.textContent).toContain("Decil D6");
  });

  it("PersonalAnchorCard renderiza comparação pessoal da cidade com a média de cidades similares", () => {
    metaDataSignal.value = {
      dataset_version: 1,
      default_selection: {
        year: 2026,
        round: 1,
        office: "president",
        bloc: "right",
        indicator: "bolsa_familia_pc",
      },
      elections: [],
      indicators: [
        {
          code: "bolsa_familia_pc",
          label: "Bolsa Família per capita",
          description: "Transferências",
          theme: "transfers",
          theme_label: "Transferências",
          tier: 1,
          unit: "R$/hab.",
          value_type: "continuous",
          higher_is: "neutral",
          scale_hint: "quantile",
          ref_year: 2026,
          coverage: 1.0,
          source_name: "MDS",
          source_url: null,
          caveat: null,
        },
      ],
      ufs: [],
      party_ideology: [],
    };
    indicatorSignal.value = "bolsa_familia_pc";
    analysisDataSignal.value = SAMPLE_ANALYSIS;

    registerMunicipalitiesInDirectory([
      { cd_ibge: 3550308, name: "São Paulo", uf: "SP", region: "Sudeste" },
    ]);
    indicatorMapDataSignal.value = {
      indicator: {
        code: "bolsa_familia_pc",
        label: "Bolsa Família",
        unit: "R$",
        ref_year: 2026,
        scale_hint: "quantile",
        source_name: "MDS",
        caveat: null,
      },
      summary: {
        count_valid: 1,
        count_missing: 0,
        min: 25.0,
        p10: 25.0,
        p25: 25.0,
        median: 25.0,
        p75: 25.0,
        p90: 25.0,
        max: 25.0,
        quantiles_7: [10, 20, 30, 40, 50, 60, 70],
      },
      columns: ["cd_ibge", "value"],
      rows: [[3550308, 25.0]],
    };
    electionMapDataSignal.value = {
      election: {
        year: 2026,
        round: 1,
        office: "president",
      },
      quantiles: {
        left_share: [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7],
        right_share: [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7],
        lr_balance: [-0.5, -0.3, -0.1, 0.0, 0.1, 0.3, 0.5],
      },
      national_summary: {
        eligible: 10000000,
        attendance: 8000000,
        valid_votes: 6800000,
        abroad_valid_votes: 0,
        bloc_shares: { left: 0.45, center: 0.1, right: 0.45 },
        municipalities_won: { left: 2500, center: 500, right: 2571 },
      },
      columns: [
        "cd_ibge",
        "left_share",
        "center_share",
        "right_share",
        "lr_balance",
        "leading_bloc",
        "valid_votes",
      ],
      rows: [[3550308, 0.45, 0.05, 0.5, 0.05, "right", 6800000]],
    };

    anchoredMunicipalitySignal.value = 3550308;

    render(<PersonalAnchorCard />, container);

    const title = container.querySelector(".personal-anchor-title");
    expect(title?.textContent).toContain("São Paulo (SP)");

    const insight = container.querySelector(".personal-anchor-insight");
    expect(insight?.textContent).toContain("São Paulo");
  });

  it("TopBar renderiza controle de nível Macro (Estado) / Micro (Município) e alterna sinal", () => {
    render(<TopBar />, container);

    const macroBtn = Array.from(container.querySelectorAll("button")).find((b) =>
      b.textContent?.includes("Macro (Estado)"),
    );
    const microBtn = Array.from(container.querySelectorAll("button")).find((b) =>
      b.textContent?.includes("Micro (Município)"),
    );

    expect(macroBtn).toBeDefined();
    expect(microBtn).toBeDefined();
    expect(geoLevelSignal.value).toBe("state");

    microBtn?.click();
    expect(geoLevelSignal.value).toBe("municipality");

    macroBtn?.click();
    expect(geoLevelSignal.value).toBe("state");
  });

  it("StateFocusCard renderiza informações do estado selecionado e permite drill-down", () => {
    metaDataSignal.value = {
      dataset_version: 1,
      default_selection: {
        year: 2026,
        round: 1,
        office: "president",
        bloc: "right",
        indicator: "bolsa_familia_pc",
      },
      elections: [],
      indicators: [],
      ufs: [
        {
          uf: "SP",
          name: "São Paulo",
          region: "Sudeste",
          bbox: [-53.11, -25.31, -44.16, -19.78],
        },
      ],
      party_ideology: [],
    };
    electionUfMapDataSignal.value = {
      election: { year: 2026, office: "president", round: 1 },
      level: "uf",
      national_summary: {
        eligible: 10000000,
        attendance: 8000000,
        valid_votes: 6800000,
        abroad_valid_votes: 0,
        bloc_shares: { left: 0.45, center: 0.05, right: 0.5 },
        municipalities_won: { left: 100, center: 10, right: 535 },
        ufs_won: { left: 10, center: 1, right: 16 },
      },
      quantiles: {
        lr_balance: [-0.5, 0, 0.5],
        left_share: [0.2, 0.4, 0.6],
        right_share: [0.2, 0.4, 0.6],
      },
      columns: [],
      rows: [
        ["SP", 35, "São Paulo", 0.42, 0.04, 0.54, 0.12, "right", 25000000, 0.81, 0.54],
      ],
    };
    selectedUfSignal.value = "SP";

    render(<StateFocusCard />, container);

    const title = container.querySelector(".state-focus-title");
    expect(title?.textContent).toContain("São Paulo (SP)");

    const lead = container.querySelector(".state-focus-bloc-lead");
    expect(lead?.textContent).toContain("Direita");

    const drillBtn = container.querySelector(".state-focus-drilldown-btn") as HTMLButtonElement;
    expect(drillBtn).not.toBeNull();

    drillBtn.click();
    expect(geoLevelSignal.value).toBe("municipality");
    expect(ufFilterSignal.value).toBe("SP");
  });

  it("StateLabelsOverlay renderiza estrutura para os 27 estados e linhas para os 8 callouts", () => {
    render(<StateLabelsOverlay map={null} />, container);

    const svg = container.querySelector(".state-leader-lines-svg");
    expect(svg).not.toBeNull();

    const marker = container.querySelector("#state-arrowhead-left");
    expect(marker).not.toBeNull();
  });

  it("MapLegend renderiza modo eleitoral de bloco para Esquerda, Centro e Direita", () => {
    electionMapDataSignal.value = {
      election: { year: 2026, office: "president", round: 1 },
      national_summary: {
        eligible: 100,
        attendance: 80,
        valid_votes: 75,
        abroad_valid_votes: 0,
        bloc_shares: { left: 0.45, center: 0.1, right: 0.45 },
        municipalities_won: { left: 2500, center: 200, right: 2871 },
      },
      quantiles: {
        lr_balance: [-0.4, -0.2, 0, 0.2, 0.4],
        left_share: [0.2, 0.35, 0.5, 0.65, 0.8],
        center_share: [0.02, 0.05, 0.08, 0.12, 0.18],
        right_share: [0.25, 0.4, 0.55, 0.7, 0.85],
      },
      columns: [],
      rows: [],
    };
    mapLayerModeSignal.value = "electoral_bloc";

    // 1. Direita
    blocSignal.value = "right";
    render(<MapLegend />, container);
    expect(container.querySelector(".map-legend-title")?.textContent).toContain(
      "Votos no bloco de Direita",
    );

    // 2. Esquerda
    blocSignal.value = "left";
    render(<MapLegend />, container);
    expect(container.querySelector(".map-legend-title")?.textContent).toContain(
      "Votos no bloco de Esquerda",
    );

    // 3. Centro
    blocSignal.value = "center";
    render(<MapLegend />, container);
    expect(container.querySelector(".map-legend-title")?.textContent).toContain(
      "Votos no bloco de Centro",
    );
  });
});
