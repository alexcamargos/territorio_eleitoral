import { describe, expect, it } from "vitest";
import {
  formatIntegerPt,
  formatDecimalPt,
  formatPctPt,
  formatPpDiffPt,
  formatRhoPt,
  formatCurrencyPt,
  formatIndicatorValuePt,
  tokenizeInsightText,
} from "../src/lib/format";

describe("lib/format — Formatação Determinística pt-BR", () => {
  it("formata inteiros com ponto como separador de milhar", () => {
    expect(formatIntegerPt(0)).toBe("0");
    expect(formatIntegerPt(5571)).toBe("5.571");
    expect(formatIntegerPt(155912680)).toBe("155.912.680");
    expect(formatIntegerPt(-14210)).toBe("-14.210");
  });

  it("formata decimais com vírgula como separador decimal", () => {
    expect(formatDecimalPt(1234.567, 2)).toBe("1.234,57");
    expect(formatDecimalPt(0.5, 1)).toBe("0,5");
  });

  it("formata percentuais com 1 casa decimal a partir de razão [0..1] ou valor [0..100]", () => {
    expect(formatPctPt(0.703, true)).toBe("70,3%");
    expect(formatPctPt(0.4412, true)).toBe("44,1%");
    expect(formatPctPt(79.51, false)).toBe("79,5%");
  });

  it("formata diferenças em pontos percentuais com sinal explícito", () => {
    expect(formatPpDiffPt(0.142, true)).toBe("+14,2 p.p.");
    expect(formatPpDiffPt(-0.085, true)).toBe("-8,5 p.p.");
    expect(formatPpDiffPt(0, true)).toBe("0,0 p.p.");
  });

  it("formata coeficiente de correlação rho com 2 casas decimais e sinal explícito", () => {
    expect(formatRhoPt(0.641)).toBe("+0,64");
    expect(formatRhoPt(-0.684)).toBe("-0,68");
    expect(formatRhoPt(0)).toBe("0,00");
  });

  it("formata valores monetários (R$) sem decimais para >= 100 e 2 casas para < 100", () => {
    expect(formatCurrencyPt(42150.4)).toBe("R$ 42.150");
    expect(formatCurrencyPt(100)).toBe("R$ 100");
    expect(formatCurrencyPt(68.5)).toBe("R$ 68,50");
    expect(formatCurrencyPt(4.12)).toBe("R$ 4,12");
  });

  it("formata valores de indicadores conforme a unidade do catálogo", () => {
    expect(formatIndicatorValuePt(89420.5, "R$")).toBe("R$ 89.421");
    expect(formatIndicatorValuePt(72.45, "R$/hab. no mês")).toBe("R$ 72,45/hab.");
    expect(formatIndicatorValuePt(64.2, "%")).toBe("64,2%");
    expect(formatIndicatorValuePt(0.742, "índice 0-1")).toBe("0,742");
    expect(formatIndicatorValuePt("A+", "ordinal A>B>C>D")).toBe("A+");
    expect(formatIndicatorValuePt(null, "R$")).toBe("Sem dado");
  });

  it("tokeniza texto de insight separando segmentos normais e trechos em **negrito**", () => {
    const raw =
      "O bloco de **direita** somou **47,7%** dos votos em **2.819** municípios ($\\rho = -0,68$, $p < 0,001$).";
    const tokens = tokenizeInsightText(raw);
    const boldTexts = tokens.filter((t) => t.bold).map((t) => t.text);
    expect(boldTexts).toEqual(["direita", "47,7%", "2.819"]);
    const fullText = tokens.map((t) => t.text).join("");
    expect(fullText).toContain("ρ = -0,68");
    expect(fullText).not.toContain("**");
    expect(fullText).not.toContain("\\rho");
  });
});
