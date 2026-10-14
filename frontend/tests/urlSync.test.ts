import { beforeEach, describe, expect, it } from "vitest";
import {
  yearSignal,
  officeSignal,
  roundSignal,
  blocSignal,
  indicatorSignal,
  ufFilterSignal,
  storyStepSignal,
  mapLayerModeSignal,
  selectedIbgeSignal,
  geoLevelSignal,
  canSelectRound2,
  resetStoreToDefaults,
} from "../src/state/store";
import {
  parseSearchParamsToStore,
  serializeStoreToSearchParams,
} from "../src/state/urlSync";

describe("state/urlSync — Sincronização Bidirecional Signals <-> Query String", () => {
  beforeEach(() => {
    resetStoreToDefaults();
  });

  it("serializa o estado padrão para URLSearchParams limpos", () => {
    const params = serializeStoreToSearchParams();
    expect(params.get("year")).toBe("2026");
    expect(params.get("office")).toBe("president");
    expect(params.get("round")).toBe("1");
    expect(params.get("bloc")).toBe("right");
    expect(params.get("step")).toBe("1");
    expect(params.get("layer")).toBe("electoral_balance");
    expect(params.get("level")).toBe("macro");
    expect(params.get("indicator")).toBeNull();
  });

  it("restaura estado completo a partir de uma query string compartilhada", () => {
    const query =
      "?year=2026&office=governor&round=2&indicator=bolsa_familia_pc&bloc=left&layer=indicator&uf=ba&mun=2927408&step=3&level=micro";
    parseSearchParamsToStore(query);

    expect(yearSignal.value).toBe(2026);
    expect(officeSignal.value).toBe("governor");
    expect(roundSignal.value).toBe(2);
    expect(indicatorSignal.value).toBe("bolsa_familia_pc");
    expect(blocSignal.value).toBe("left");
    expect(mapLayerModeSignal.value).toBe("indicator");
    expect(ufFilterSignal.value).toBe("BA");
    expect(selectedIbgeSignal.value).toBe(2927408);
    expect(geoLevelSignal.value).toBe("municipality");
    expect(storyStepSignal.value).toBe(3);
  });

  it("força round=1 quando o cargo não possui 2º turno (ex.: senator, federal_deputy)", () => {
    parseSearchParamsToStore("?office=senator&round=2");
    expect(officeSignal.value).toBe("senator");
    expect(canSelectRound2.value).toBe(false);
    expect(roundSignal.value).toBe(1);
  });

  it("promove storyStep automaticamente para 3 se indicator estiver presente na URL com step=1", () => {
    parseSearchParamsToStore("?indicator=gdp_per_capita&step=1");
    expect(indicatorSignal.value).toBe("gdp_per_capita");
    expect(storyStepSignal.value).toBe(3);
    expect(mapLayerModeSignal.value).toBe("indicator");
  });
});
