/**
 * Deterministic Brazilian Portuguese (pt-BR) number and text formatting utilities.
 * Never depends on OS/browser locale settings (`docs/07-metodologia.md` §5.3).
 */

import type { BlocCode, OfficeCode } from "../types/api";

export interface InsightTextToken {
  text: string;
  bold: boolean;
}

/**
 * Formats an integer using `.` as thousands separator.
 */
export function formatIntegerPt(value: number): string {
  if (!Number.isFinite(value)) {
    return "—";
  }
  const rounded = Math.round(value);
  const sign = rounded < 0 ? "-" : "";
  const digits = Math.abs(rounded).toString();
  const grouped = digits.replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  return `${sign}${grouped}`;
}

/**
 * Formats a floating-point number using `,` as decimal separator and `.` for thousands.
 */
export function formatDecimalPt(value: number, decimals = 2): string {
  if (!Number.isFinite(value)) {
    return "—";
  }
  const factor = 10 ** decimals;
  const rounded = Math.round(value * factor) / factor;
  const sign = rounded < 0 ? "-" : "";
  const absFixed = Math.abs(rounded).toFixed(decimals);
  const [intPart = "0", decPart] = absFixed.split(".");
  const groupedInt = intPart.replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  if (decimals <= 0 || decPart === undefined) {
    return `${sign}${groupedInt}`;
  }
  return `${sign}${groupedInt},${decPart}`;
}

/**
 * Formats a percentage with 1 decimal place (`70,3%`).
 */
export function formatPctPt(
  value: number,
  isRatio = true,
  decimals = 1,
): string {
  if (!Number.isFinite(value)) {
    return "—";
  }
  const pct = isRatio ? value * 100 : value;
  return `${formatDecimalPt(pct, decimals)}%`;
}

/**
 * Formats a percentage-point difference with an explicit sign (`+14,2 p.p.` or `-8,5 p.p.`).
 */
export function formatPpDiffPt(diff: number, isRatio = true): string {
  if (!Number.isFinite(diff)) {
    return "—";
  }
  const pp = isRatio ? diff * 100 : diff;
  const rounded = Math.round(pp * 10) / 10;
  if (Math.abs(rounded) < 1e-9) {
    return "0,0 p.p.";
  }
  const sign = rounded > 0 ? "+" : "";
  return `${sign}${formatDecimalPt(rounded, 1)} p.p.`;
}

/**
 * Formats a Spearman or Pearson correlation coefficient with 2 decimals and sign (`+0,64`).
 */
export function formatRhoPt(rho: number): string {
  if (!Number.isFinite(rho)) {
    return "—";
  }
  const rounded = Math.round(rho * 100) / 100;
  if (Math.abs(rounded) < 1e-9) {
    return "0,00";
  }
  const sign = rounded > 0 ? "+" : "";
  return `${sign}${formatDecimalPt(rounded, 2)}`;
}

/**
 * Formats a currency value (`R$`): no decimals when >= 100, 2 decimals when < 100.
 */
export function formatCurrencyPt(value: number): string {
  if (!Number.isFinite(value)) {
    return "—";
  }
  if (Math.abs(value) >= 100) {
    return `R$ ${formatIntegerPt(value)}`;
  }
  return `R$ ${formatDecimalPt(value, 2)}`;
}

/**
 * Formats any indicator value according to its unit string from `indicators.yaml`.
 */
export function formatIndicatorValuePt(
  value: number | string | null | undefined,
  unit: string,
): string {
  if (value === null || value === undefined) {
    return "Sem dado";
  }
  if (typeof value === "string") {
    return value;
  }
  if (!Number.isFinite(value)) {
    return "Sem dado";
  }

  const normalizedUnit = unit.trim().toLowerCase();
  if (normalizedUnit === "r$") {
    return formatCurrencyPt(value);
  }
  if (normalizedUnit.startsWith("r$/hab")) {
    return `${formatCurrencyPt(value)}/hab.`;
  }
  if (normalizedUnit === "%") {
    return `${formatDecimalPt(value, 1)}%`;
  }
  if (normalizedUnit === "pessoas") {
    return formatIntegerPt(value);
  }
  if (normalizedUnit === "km²") {
    return `${formatDecimalPt(value, 1)} km²`;
  }
  if (normalizedUnit === "hab./km²") {
    return `${formatDecimalPt(value, 1)} hab./km²`;
  }
  if (normalizedUnit.includes("0-1") && !normalizedUnit.includes("0-10")) {
    return formatDecimalPt(value, 3);
  }
  if (normalizedUnit.includes("0-10") && !normalizedUnit.includes("0-100")) {
    return formatDecimalPt(value, 1);
  }
  if (normalizedUnit.includes("0-100")) {
    return formatDecimalPt(value, 1);
  }
  if (Math.abs(value) >= 1000) {
    return formatIntegerPt(value);
  }
  return formatDecimalPt(value, 1);
}

/**
 * Formats an indicator value compactly for tight chart axes and legend bins
 * (e.g., `R$ 13,5 mil`, `R$ 679 mil`, `1,2 mi`).
 */
export function formatCompactValuePt(
  value: number | string | null | undefined,
  unit: string,
  includeCurrencyPrefix = true,
): string {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return formatIndicatorValuePt(value, unit);
  }
  const normalizedUnit = unit.trim().toLowerCase();
  const isCurrency =
    normalizedUnit === "r$" || normalizedUnit.startsWith("r$/hab");
  const prefix = isCurrency && includeCurrencyPrefix ? "R$ " : "";
  const abs = Math.abs(value);

  if (abs >= 1_000_000) {
    return `${prefix}${formatDecimalPt(value / 1_000_000, 1)} mi`;
  }
  if (abs >= 20_000) {
    return `${prefix}${formatDecimalPt(value / 1_000, 0)} mil`;
  }
  if (abs >= 1_000) {
    return `${prefix}${formatDecimalPt(value / 1_000, 1)} mil`;
  }
  return isCurrency && !includeCurrencyPrefix
    ? formatIntegerPt(value)
    : formatIndicatorValuePt(value, unit);
}

/**
 * Tokenizes deterministic insight text containing `**bold**` markers and basic LaTeX symbols
 * into safe tokens for Preact rendering without `dangerouslySetInnerHTML`.
 */
export function tokenizeInsightText(raw: string): InsightTextToken[] {
  const cleaned = raw
    .replace(/\\rho/g, "ρ")
    .replace(/(?<!R)\$([^$]+)\$/g, "$1");

  const parts = cleaned.split(/(\*\*[^*]+\*\*)/g);
  const tokens: InsightTextToken[] = [];

  for (const part of parts) {
    if (!part) {
      continue;
    }
    if (part.startsWith("**") && part.endsWith("**") && part.length > 4) {
      tokens.push({
        text: part.slice(2, -2),
        bold: true,
      });
    } else {
      tokens.push({
        text: part,
        bold: false,
      });
    }
  }
  return tokens;
}

export const BLOC_LABELS_PT: Record<BlocCode, string> = {
  left: "Esquerda",
  center: "Centro",
  right: "Direita",
};

export const OFFICE_LABELS_PT: Record<OfficeCode, string> = {
  president: "Presidente",
  governor: "Governador",
  senator: "Senador",
  federal_deputy: "Deputado Federal",
  state_deputy: "Deputado Estadual",
  district_deputy: "Deputado Distrital",
  state_or_district_deputy: "Deputado Estadual / Distrital",
};
