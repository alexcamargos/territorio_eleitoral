import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiClient, ApiClientError } from "../src/services/apiClient";

describe("services/apiClient — Cache em Memória, ETag e AbortController", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("retorna resposta do cache quando o servidor responde 304 Not Modified com ETag", async () => {
    const mockFetch = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ status: "ok", municipality_count: 5571 }), {
          status: 200,
          headers: {
            "Content-Type": "application/json",
            ETag: 'W/"dv1-abc"',
          },
        }),
      )
      .mockResolvedValueOnce(
        new Response(null, {
          status: 304,
          headers: { ETag: 'W/"dv1-abc"' },
        }),
      );

    const client = new ApiClient(mockFetch as unknown as typeof fetch);

    const first = await client.getJson<{ status: string; municipality_count: number }>(
      "/api/v1/health",
      { revalidate: true },
    );
    expect(first.municipality_count).toBe(5571);

    const second = await client.getJson<{ status: string; municipality_count: number }>(
      "/api/v1/health",
      { revalidate: true },
    );
    expect(second.municipality_count).toBe(5571);
    expect(mockFetch).toHaveBeenCalledTimes(2);

    const secondCallInit = mockFetch.mock.calls[1]?.[1] as RequestInit | undefined;
    const headers = secondCallInit?.headers as Record<string, string> | undefined;
    expect(headers?.["If-None-Match"]).toBe('W/"dv1-abc"');
  });

  it("lança ApiClientError estruturado quando a API retorna erro RFC 9457", async () => {
    const mockFetch = vi.fn().mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          error: {
            code: "INDICATOR_NOT_FOUND",
            message: "O indicador 'foo' não existe.",
            details: { indicator_code: "foo" },
          },
        }),
        { status: 404, headers: { "Content-Type": "application/json" } },
      ),
    );

    const client = new ApiClient(mockFetch as unknown as typeof fetch);
    await expect(client.getJson("/api/v1/indicators/foo/map")).rejects.toThrowError(
      ApiClientError,
    );
  });

  it("aborta requisição anterior da mesma chave (cancelKey) quando uma nova é disparada", async () => {
    let capturedSignal: AbortSignal | undefined;
    const mockFetch = vi.fn().mockImplementation((_url: string, init?: RequestInit) => {
      if (!capturedSignal) {
        capturedSignal = init?.signal ?? undefined;
        return new Promise((_resolve, reject) => {
          init?.signal?.addEventListener("abort", () => {
            reject(new DOMException("Aborted", "AbortError"));
          });
        });
      }
      return Promise.resolve(
        new Response(JSON.stringify({ items: [] }), { status: 200 }),
      );
    });

    const client = new ApiClient(mockFetch as unknown as typeof fetch);
    const p1 = client.getJson("/api/v1/municipalities/search?q=sa", {
      cancelKey: "search",
    });
    const p2 = client.getJson<{ items: unknown[] }>(
      "/api/v1/municipalities/search?q=sao",
      { cancelKey: "search" },
    );

    expect(capturedSignal?.aborted).toBe(true);
    await expect(p1).rejects.toThrow();
    const res2 = await p2;
    expect(res2.items).toEqual([]);
  });
});
