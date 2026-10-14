/**
 * Typed HTTP client with in-memory caching, ETag (`If-None-Match` / `304`) support,
 * and automatic concurrency cancellation via `AbortController` (`docs/09-frontend.md` §1).
 */

import type {
  AnalysisResponse,
  ApiErrorEnvelope,
  BlocCode,
  ElectionMapResponse,
  IndicatorMapResponse,
  MetaResponse,
  MunicipalityProfileResponse,
  MunicipalitySearchResponse,
  OfficeCode,
} from "../types/api";

export class ApiClientError extends Error {
  public readonly statusCode: number;
  public readonly code: string;
  public readonly details?: Record<string, unknown>;

  constructor(
    statusCode: number,
    code: string,
    message: string,
    details?: Record<string, unknown>,
  ) {
    super(message);
    this.name = "ApiClientError";
    this.statusCode = statusCode;
    this.code = code;
    this.details = details;
  }
}

interface CacheEntry<T> {
  etag: string | null;
  data: T;
}

export interface RequestOptions {
  cancelKey?: string;
  revalidate?: boolean;
}

export class ApiClient {
  private readonly fetchImpl: typeof fetch;
  private readonly cache = new Map<string, CacheEntry<unknown>>();
  private readonly inflightControllers = new Map<string, AbortController>();

  constructor(fetchImpl?: typeof fetch) {
    this.fetchImpl = fetchImpl ?? ((...args) => globalThis.fetch(...args));
  }

  /**
   * Performs a typed GET request with in-memory + ETag caching and optional cancellation.
   */
  public async getJson<T>(url: string, options?: RequestOptions): Promise<T> {
    const cancelKey = options?.cancelKey;
    if (cancelKey) {
      const prevController = this.inflightControllers.get(cancelKey);
      if (prevController) {
        prevController.abort();
      }
    }

    const cached = this.cache.get(url) as CacheEntry<T> | undefined;
    if (cached && !options?.revalidate) {
      return cached.data;
    }

    const controller = new AbortController();
    if (cancelKey) {
      this.inflightControllers.set(cancelKey, controller);
    }

    const headers: Record<string, string> = {
      Accept: "application/json",
    };
    if (cached?.etag) {
      headers["If-None-Match"] = cached.etag;
    }

    try {
      const response = await this.fetchImpl(url, {
        method: "GET",
        headers,
        signal: controller.signal,
      });

      if (response.status === 304 && cached) {
        return cached.data;
      }

      if (!response.ok) {
        let errorCode = `HTTP_${response.status}`;
        let errorMessage = `Falha na requisição (${response.status}).`;
        let errorDetails: Record<string, unknown> | undefined;

        try {
          const body = (await response.json()) as Partial<ApiErrorEnvelope>;
          if (body.error) {
            errorCode = body.error.code || errorCode;
            errorMessage = body.error.message || errorMessage;
            errorDetails = body.error.details;
          }
        } catch {
          // Non-JSON error body
        }

        throw new ApiClientError(
          response.status,
          errorCode,
          errorMessage,
          errorDetails,
        );
      }

      const data = (await response.json()) as T;
      const etag = response.headers.get("ETag");
      this.cache.set(url, { etag, data });
      return data;
    } finally {
      if (cancelKey && this.inflightControllers.get(cancelKey) === controller) {
        this.inflightControllers.delete(cancelKey);
      }
    }
  }

  public fetchMeta(): Promise<MetaResponse> {
    return this.getJson<MetaResponse>("/api/v1/meta", { cancelKey: "meta" });
  }

  public fetchElectionMap(
    year: number,
    office: OfficeCode,
    round: 1 | 2,
    uf?: string | null,
    level?: "state" | "municipality",
  ): Promise<ElectionMapResponse> {
    const params = new URLSearchParams();
    if (uf) {
      params.set("uf", uf);
    }
    if (level === "state") {
      params.set("level", "uf");
    }
    const qs = params.toString();
    const suffix = qs ? `?${qs}` : "";
    return this.getJson<ElectionMapResponse>(
      `/api/v1/elections/${year}/${office}/${round}/map${suffix}`,
      { cancelKey: "electionMap" },
    );
  }

  public fetchIndicatorMap(
    code: string,
    uf?: string | null,
    refYear?: number | null,
    level?: "state" | "municipality",
  ): Promise<IndicatorMapResponse> {
    const params = new URLSearchParams();
    if (uf) {
      params.set("uf", uf);
    }
    if (refYear) {
      params.set("ref_year", String(refYear));
    }
    if (level === "state") {
      params.set("level", "uf");
    }
    const qs = params.toString();
    const suffix = qs ? `?${qs}` : "";
    return this.getJson<IndicatorMapResponse>(
      `/api/v1/indicators/${encodeURIComponent(code)}/map${suffix}`,
      { cancelKey: "indicatorMap" },
    );
  }

  public fetchAnalysis(params: {
    year: number;
    office: OfficeCode;
    round: 1 | 2;
    indicator: string;
    bloc: BlocCode;
    uf?: string | null;
    level?: "state" | "municipality";
  }): Promise<AnalysisResponse> {
    const search = new URLSearchParams({
      year: String(params.year),
      office: params.office,
      round: String(params.round),
      indicator: params.indicator,
      bloc: params.bloc,
    });
    if (params.uf) {
      search.set("uf", params.uf);
    }
    if (params.level === "state") {
      search.set("level", "uf");
    }
    return this.getJson<AnalysisResponse>(
      `/api/v1/analysis?${search.toString()}`,
      { cancelKey: "analysis" },
    );
  }

  public searchMunicipalities(
    q: string,
    limit = 10,
  ): Promise<MunicipalitySearchResponse> {
    const search = new URLSearchParams({
      q: q.trim(),
      limit: String(limit),
    });
    return this.getJson<MunicipalitySearchResponse>(
      `/api/v1/municipalities/search?${search.toString()}`,
      { cancelKey: "municipalitySearch", revalidate: false },
    );
  }

  public fetchMunicipalityProfile(
    cdIbge: number,
    year = 2026,
    round: 1 | 2 = 1,
  ): Promise<MunicipalityProfileResponse> {
    const search = new URLSearchParams({
      year: String(year),
      round: String(round),
    });
    return this.getJson<MunicipalityProfileResponse>(
      `/api/v1/municipalities/${cdIbge}?${search.toString()}`,
      { cancelKey: "municipalityProfile" },
    );
  }
}

export const apiClient = new ApiClient();
