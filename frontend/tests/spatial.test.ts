import { describe, expect, it } from "vitest";
import {
  buildSpatialIndex,
  computePointRadius,
  type ScreenScatterPoint,
} from "../src/lib/spatial";

describe("lib/spatial — Índice Espacial e Hit-Testing do ScatterPlot", () => {
  const samplePoints: ScreenScatterPoint[] = [
    {
      cdIbge: 3550308,
      px: 100,
      py: 120,
      radius: 7,
      xVal: 89420,
      yVal: 0.4378,
      validVotes: 6812440,
      region: "Sudeste",
    },
    {
      cdIbge: 1100015,
      px: 200,
      py: 80,
      radius: 3,
      xVal: 72.45,
      yVal: 0.6547,
      validVotes: 14210,
      region: "Norte",
    },
  ];

  it("encontra o ponto mais próximo dentro do raio máximo (12px)", () => {
    const index = buildSpatialIndex(samplePoints);
    const hit = index.findNearest(104, 118, 12);
    expect(hit?.cdIbge).toBe(3550308);
  });

  it("retorna null quando o cursor está a mais de 12px de qualquer ponto", () => {
    const index = buildSpatialIndex(samplePoints);
    const miss = index.findNearest(150, 150, 12);
    expect(miss).toBeNull();
  });

  it("calcula o raio em pixels entre 2.5px e 7.0px proporcional à raiz de valid_votes", () => {
    expect(computePointRadius(0, 6800000)).toBeCloseTo(2.5, 2);
    expect(computePointRadius(6800000, 6800000)).toBeCloseTo(7.0, 2);
    const mid = computePointRadius(100000, 6800000);
    expect(mid).toBeGreaterThan(2.5);
    expect(mid).toBeLessThan(7.0);
  });
});
