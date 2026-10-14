"""HTTP ETag computation, `If-None-Match` short-circuiting, and Cache-Control."""

import hashlib

from fastapi import Request, Response

API_CACHE_CONTROL = "public, max-age=300, stale-while-revalidate=3600"
TILE_CACHE_CONTROL = "public, max-age=86400, immutable"


def compute_etag(dataset_version_id: int, path_and_query: str) -> str:
    """Computes a weak ETag tied to `dataset_version_id` and normalized request URL.

    Args:
        dataset_version_id: Currently published `dataset_version.id`.
        path_and_query: Request path and sorted query string.

    Returns:
        Weak ETag string `W/"dv{id}-{sha1_12}"`.
    """
    short_hash = hashlib.sha1(path_and_query.encode("utf-8")).hexdigest()[:12]
    return f'W/"dv{int(dataset_version_id)}-{short_hash}"'


def normalize_request_key(request: Request) -> str:
    """Builds a canonical `path?sorted_query` key for ETag hashing.

    Args:
        request: FastAPI `Request` object.

    Returns:
        Canonical request key string.
    """
    items = sorted(request.query_params.multi_items())
    if not items:
        return request.url.path
    query_str = "&".join(f"{k}={v}" for k, v in items)
    return f"{request.url.path}?{query_str}"


def check_not_modified_or_set_headers(
    request: Request,
    response: Response,
    dataset_version_id: int,
    *,
    is_tile: bool = False,
) -> Response | None:
    """Checks `If-None-Match` against the dataset ETag and sets cache headers.

    Args:
        request: Incoming FastAPI `Request`.
        response: Outgoing FastAPI `Response` to populate headers on.
        dataset_version_id: Published `dataset_version.id`.
        is_tile: Whether the endpoint serves immutable MVT vector tiles.

    Returns:
        A `304 Not Modified` `Response` if `If-None-Match` matches, or `None`
        when the route handler should proceed normally.
    """
    etag = compute_etag(dataset_version_id, normalize_request_key(request))
    cache_ctrl = TILE_CACHE_CONTROL if is_tile else API_CACHE_CONTROL
    headers = {
        "ETag": etag,
        "X-Dataset-Version": str(int(dataset_version_id)),
        "Cache-Control": cache_ctrl,
    }
    inm = request.headers.get("if-none-match")
    if inm and inm.strip() == etag:
        return Response(status_code=304, headers=headers)

    for k, v in headers.items():
        response.headers[k] = v
    return None


compute_weak_etag = compute_etag


def is_etag_matched(request: Request, etag: str) -> bool:
    """Checks whether the request `If-None-Match` header matches `etag`.

    Args:
        request: Incoming FastAPI `Request`.
        etag: Computed ETag string.

    Returns:
        True if `If-None-Match` matches `etag`.
    """
    inm = request.headers.get("if-none-match")
    return bool(inm and inm.strip() == etag)


def apply_etag_and_cache(
    request: Request,
    response: Response,
    *,
    dataset_version_id: int,
    route_key: str | None = None,
) -> Response | None:
    """Applies ETag and Cache-Control headers and returns 304 if `If-None-Match` hits.

    Args:
        request: Incoming FastAPI `Request`.
        response: Outgoing FastAPI `Response`.
        dataset_version_id: Published `dataset_version.id`.
        route_key: Optional explicit key override.

    Returns:
        `Response(status_code=304)` if `If-None-Match` matches, else `None`.
    """
    _ = route_key
    return check_not_modified_or_set_headers(request, response, dataset_version_id)
