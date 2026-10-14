import { describe, expect, it } from "vitest";
import {
  PALETTES,
  getElectoralPalette,
  getIndicatorPalette,
  buildMapLibreColorExpression,
  buildLegendBins,
  encodeIndicatorRowsForMap,
  computeDecileMembership,
} from "../src/lib/scales";
import type { ThemeCode } from "../src/types/api";

describe("lib/scales — Governança Cromática (ADR-006) e Escalas Cartográficas", () => {
  const INDICATOR_THEMES: ThemeCode[] = [
    "economy",
    "transfers",
    "social",
    "education",
    "health",
    "infrastructure",
    "fiscal",
    "composite",
    "electoral",
  ];

  const ELECTORAL_HEX_SET = new Set<string>([
    ...PALETTES.DivergingLeftRight.map((c) => c.toUpperCase()),
    ...PALETTES.SequentialLeft.map((c) => c.toUpperCase()),
    ...PALETTES.SequentialRight.map((c) => c.toUpperCase()),
  ]);

  it("garante que todas as paletas possuem exatamente 7 stops hexadecimais", () => {
    for (const [name, stops] of Object.entries(PALETTES)) {
      expect(stops, `Paleta ${name} deve ter 7 stops`).toHaveLength(7);
      for (const hex of stops) {
        expect(hex).toMatch(/^#[0-9A-Fa-f]{6}$/);
      }
    }
  });

  it("REGRA INEGOCIÁVEL #6 (ADR-006): nenhum tema de indicador recebe paleta vermelho/azul eleitoral", () => {
    for (const theme of INDICATOR_THEMES) {
      const palette = getIndicatorPalette(theme);
      expect(palette).toHaveLength(7);
      for (const color of palette) {
        expect(
          ELECTORAL_HEX_SET.has(color.toUpperCase()),
          `Tema '${theme}' colidiu com cor eleitoral reservada: ${color}`,
        ).toBe(false);
      }
    }
  });

  it("retorna a paleta eleitoral correta para saldo e blocos", () => {
    expect(getElectoralPalette("electoral_balance", "right")).toEqual(
      PALETTES.DivergingLeftRight,
    );
    expect(getElectoralPalette("electoral_bloc", "left")).toEqual(
      PALETTES.SequentialLeft,
    );
    expect(getElectoralPalette("electoral_bloc", "right")).toEqual(
      PALETTES.SequentialRight,
    );
    expect(getElectoralPalette("electoral_bloc", "center")).toEqual(
      PALETTES.SequentialCenter,
    );
  });

  it("constrói expressão MapLibre step com fallback para metric === null", () => {
    const thresholds = [-0.5, -0.2, -0.05, 0.05, 0.2, 0.5];
    const expr = buildMapLibreColorExpression(
      thresholds,
      PALETTES.DivergingLeftRight,
      "#D6D3CD",
    );
    expect(Array.isArray(expr)).toBe(true);
    expect(expr[0]).toBe("case");
    // Fallback para null deve ser a cor nodata
    expect(expr[2]).toBe("#D6D3CD");
  });

  it("gera 7 faixas de legenda a partir de quantiles_7 ou breakpoints", () => {
    const q7 = [4.12, 22.1, 38.4, 57.0, 89.3, 138.2, 198.7, 412.9];
    const bins = buildLegendBins(q7, PALETTES.SequentialAmberPurple);
    expect(bins).toHaveLength(7);
    expect(bins[0]?.min).toBe(4.12);
    expect(bins[0]?.max).toBe(22.1);
    expect(bins[6]?.max).toBe(412.9);
  });

  it("codifica valores categóricos/ordinais (ex.: CAPAG A+, A, B, C) em índices numéricos para feature-state", () => {
    const rows = [
      [1100015, "B"],
      [3550308, "A+"],
      [5101837, null],
      [3304557, "C"],
    ] as const;
    const encoded = encodeIndicatorRowsForMap(rows, "ordinal");
    expect(encoded.numericRows).toHaveLength(4);
    expect(encoded.numericRows[2]).toEqual([5101837, null]);
    expect(encoded.categories).toEqual(["A+", "B", "C"]);
  });

  it("particiona municípios em 10 decis determinísticos desempatando por cd_ibge", () => {
    const rows: [number, number][] = [];
    for (let i = 1; i <= 20; i++) {
      rows.push([1000000 + i, i * 10]);
    }
    const decileMap = computeDecileMembership(rows);
    expect(decileMap.get(1000001)).toBe(1);
    expect(decileMap.get(1000002)).toBe(1);
    expect(decileMap.get(1000019)).toBe(10);
    expect(decileMap.get(1000020)).toBe(10);
  });
});
