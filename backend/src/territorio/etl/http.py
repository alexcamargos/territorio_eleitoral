"""Resilient HTTP client with disk caching, SHA-256 verification, and rate limiting."""

import hashlib
import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

USER_AGENT = "territorio-eleitoral/0.1 (+https://github.com/territorio-eleitoral)"


def _is_retryable_http_error(exc: BaseException) -> bool:
    """Determines whether an HTTP exception is transient and should be retried.

    Args:
        exc: Exception raised during an HTTP call.

    Returns:
        True if the exception is a transport error, 429 rate limit, or 5xx server error.
    """
    if isinstance(exc, httpx.TransportError):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        return status == 429 or status >= 500
    return False


@dataclass(frozen=True, slots=True)
class CachedArtifact:
    """Metadata describing a downloaded and cached file on disk.

    Attributes:
        path: Local filesystem path of the cached payload.
        url: Source URL from which the payload was fetched.
        sha256: Hexadecimal SHA-256 digest of the file.
        fetched_at: ISO-8601 UTC timestamp of the download.
        last_modified: Optional HTTP Last-Modified header value from the server.
        from_cache: True if the file was served from local cache without network I/O.
    """

    path: Path
    url: str
    sha256: str
    fetched_at: str
    last_modified: str | None
    from_cache: bool


class TokenBucketRateLimiter:
    """Enforces a maximum request rate per minute using monotonic clock intervals.

    Attributes:
        rate_per_min: Maximum number of requests allowed per minute.
        min_interval_s: Minimum interval in seconds between consecutive calls.
    """

    def __init__(
        self,
        rate_per_min: int | None = None,
        *,
        rate_per_minute: int | None = None,
    ) -> None:
        """Initializes the rate limiter.

        Args:
            rate_per_min: Allowed requests per minute (must be > 0).
            rate_per_minute: Alias for `rate_per_min` (must be > 0).

        Raises:
            ValueError: If the rate is missing or less than or equal to zero.
        """
        resolved_rate = rate_per_min if rate_per_min is not None else rate_per_minute
        if resolved_rate is None or resolved_rate <= 0:
            raise ValueError(f"rate_per_min must be positive, got {resolved_rate}")
        self.rate_per_min = resolved_rate
        self.min_interval_s = 60.0 / float(resolved_rate)
        self._last_call: float | None = None

    def acquire(self) -> None:
        """Blocks until the next request slot is available."""
        now = time.monotonic()
        if self._last_call is not None:
            elapsed = now - self._last_call
            remaining = self.min_interval_s - elapsed
            if remaining > 0:
                time.sleep(remaining)
                now = time.monotonic()
        self._last_call = now


class CachedHttpClient:
    """HTTP client wrapper providing retry, rate limiting, and SHA-256 disk caching.

    Attributes:
        cache_root: Root directory for cached raw downloads (`data/raw`).
        timeout_s: Request timeout in seconds.
    """

    def __init__(
        self,
        cache_root: Path,
        timeout_s: float = 60.0,
        rate_limiter: TokenBucketRateLimiter | None = None,
    ) -> None:
        """Initializes the cached HTTP client.

        Args:
            cache_root: Base directory where source subdirectories will be created.
            timeout_s: Timeout in seconds for HTTP operations.
            rate_limiter: Optional rate limiter applied before network requests.
        """
        self.cache_root = cache_root
        self.timeout_s = timeout_s
        self._rate_limiter = rate_limiter
        self._client = httpx.Client(
            timeout=httpx.Timeout(timeout_s, connect=15.0),
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
        )

    def close(self) -> None:
        """Closes the underlying httpx client."""
        self._client.close()

    def __enter__(self) -> "CachedHttpClient":
        """Enters the context manager.

        Returns:
            Self instance.
        """
        return self

    def __exit__(self, *args: object) -> None:
        """Closes the client when leaving the context manager.

        Args:
            *args: Exception info tuple.
        """
        self.close()

    def _meta_path(self, target_path: Path) -> Path:
        """Returns the sidecar metadata path for a cached file.

        Args:
            target_path: Path to the cached data file.

        Returns:
            Sidecar `.meta.json` path.
        """
        return target_path.with_suffix(target_path.suffix + ".meta.json")

    def _read_cached_artifact(
        self, target_path: Path, url: str
    ) -> CachedArtifact | None:
        """Loads cached artifact metadata if both file and sidecar exist.

        Args:
            target_path: Path to the cached file.
            url: Expected source URL.

        Returns:
            CachedArtifact with `from_cache=True` if valid cache exists, else None.
        """
        meta_file = self._meta_path(target_path)
        if not target_path.exists() or not meta_file.exists():
            return None
        try:
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
            return CachedArtifact(
                path=target_path,
                url=meta.get("url", url),
                sha256=meta["sha256"],
                fetched_at=meta["fetched_at"],
                last_modified=meta.get("last_modified"),
                from_cache=True,
            )
        except (KeyError, ValueError, OSError):
            return None

    def _write_sidecar(
        self,
        target_path: Path,
        *,
        url: str,
        sha256: str,
        fetched_at: str,
        last_modified: str | None,
    ) -> None:
        """Writes sidecar metadata JSON for a downloaded file.

        Args:
            target_path: Path to the downloaded file.
            url: Source URL.
            sha256: Computed SHA-256 hex digest.
            fetched_at: UTC ISO-8601 timestamp.
            last_modified: Optional HTTP Last-Modified header value.
        """
        meta_file = self._meta_path(target_path)
        meta_file.write_text(
            json.dumps(
                {
                    "url": url,
                    "sha256": sha256,
                    "fetched_at": fetched_at,
                    "last_modified": last_modified,
                },
                indent=2,
            ),
            encoding="utf-8",
        )

    @retry(
        retry=retry_if_exception(_is_retryable_http_error),
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1.0, min=1.0, max=16.0),
        reraise=True,
    )
    def _stream_to_disk(
        self,
        url: str,
        target_path: Path,
        headers: dict[str, str] | None = None,
    ) -> tuple[str, str | None]:
        """Streams a URL response to a temporary file and atomically renames it.

        Args:
            url: Target URL to download.
            target_path: Final destination path on disk.
            headers: Optional extra HTTP request headers.

        Returns:
            Tuple of `(sha256_hex, last_modified_header)`.

        Raises:
            httpx.HTTPStatusError: If the server returns a non-success status.
            httpx.TransportError: If a network error occurs across all retries.
        """
        if self._rate_limiter is not None:
            self._rate_limiter.acquire()

        target_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_file = target_path.with_suffix(target_path.suffix + ".part")
        hasher = hashlib.sha256()

        with self._client.stream("GET", url, headers=headers) as response:
            response.raise_for_status()
            last_modified = response.headers.get("Last-Modified")
            with tmp_file.open("wb") as fh:
                for chunk in response.iter_bytes(chunk_size=65536):
                    fh.write(chunk)
                    hasher.update(chunk)

        tmp_file.replace(target_path)
        return hasher.hexdigest(), last_modified

    def download(
        self,
        url_pos: str | None = None,
        *,
        source: str | None = None,
        subdir: str | None = None,
        url: str | None = None,
        filename: str | None = None,
        force_refresh: bool = False,
        headers: dict[str, str] | None = None,
    ) -> CachedArtifact:
        """Downloads a binary or text file with disk caching and SHA-256 computation.

        Args:
            url_pos: Optional positional URL to fetch.
            source: Source namespace folder under `data/raw/`.
            subdir: Alias for `source` namespace folder under `data/raw/`.
            url: Full HTTP/HTTPS URL to fetch (when passed by keyword).
            filename: Relative file name inside `data/raw/{source}/`.
            force_refresh: If True, bypasses local cache and re-downloads.
            headers: Optional extra HTTP headers.

        Returns:
            CachedArtifact containing the local path and SHA-256 digest.

        Raises:
            ValueError: If no URL is provided.
        """
        target_url = url_pos or url
        if not target_url:
            raise ValueError("download() requires a URL.")
        target_source = source or subdir or "http"
        target_filename = filename or (
            Path(urlparse(target_url).path).name or "download.bin"
        )
        target_path = self.cache_root / target_source / target_filename
        if not force_refresh:
            cached = self._read_cached_artifact(target_path, target_url)
            if cached is not None:
                return cached

        sha256, last_modified = self._stream_to_disk(
            target_url, target_path, headers=headers
        )
        fetched_at = datetime.now(UTC).isoformat()
        self._write_sidecar(
            target_path,
            url=target_url,
            sha256=sha256,
            fetched_at=fetched_at,
            last_modified=last_modified,
        )
        return CachedArtifact(
            path=target_path,
            url=target_url,
            sha256=sha256,
            fetched_at=fetched_at,
            last_modified=last_modified,
            from_cache=False,
        )

    @retry(
        retry=retry_if_exception(_is_retryable_http_error),
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1.0, min=1.0, max=16.0),
        reraise=True,
    )
    def _fetch_bytes(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        params: dict[str, str | int] | None = None,
    ) -> tuple[bytes, str | None]:
        """Performs a retried GET request returning raw bytes and Last-Modified.

        Args:
            url: Target URL.
            headers: Optional request headers.
            params: Optional query parameters.

        Returns:
            Tuple of `(response_bytes, last_modified)`.

        Raises:
            httpx.HTTPStatusError: On non-2xx HTTP status codes.
            httpx.TransportError: On network transport errors.
        """
        if self._rate_limiter is not None:
            self._rate_limiter.acquire()
        response = self._client.get(url, headers=headers, params=params)
        response.raise_for_status()
        return response.content, response.headers.get("Last-Modified")

    def get_json(
        self,
        url_pos: str | None = None,
        *,
        source: str | None = None,
        url: str | None = None,
        cache_key: str | None = None,
        force_refresh: bool = False,
        headers: dict[str, str] | None = None,
        params: dict[str, str | int] | None = None,
    ) -> tuple[Any, Any]:
        """Fetches a JSON endpoint, caching the raw payload on disk with SHA-256.

        When `cache_key` is provided explicitly, returns `(parsed_json,
        CachedArtifact)`. When called positionally without `cache_key`, auto-derives
        a deterministic cache key and returns `(parsed_json, sha256_str)`.

        Args:
            url_pos: Optional positional endpoint URL.
            source: Source namespace folder under `data/raw/`.
            url: Endpoint URL (when passed by keyword).
            cache_key: Relative path inside `data/raw/{source}/` for the JSON file.
            force_refresh: If True, ignores existing cached file.
            headers: Optional HTTP headers (e.g. `chave-api-dados`).
            params: Optional query string parameters.

        Returns:
            Tuple of `(parsed_json, CachedArtifact)` if `cache_key` was specified,
            or `(parsed_json, sha256_hex)` otherwise.

        Raises:
            ValueError: If no URL is provided.
        """
        target_url = url_pos or url
        if not target_url:
            raise ValueError("get_json() requires a URL.")
        return_artifact = cache_key is not None
        target_source = source or "http_json"
        target_key = cache_key or (
            f"{hashlib.sha256(target_url.encode('utf-8')).hexdigest()[:24]}.json"
        )
        target_path = self.cache_root / target_source / target_key
        if not force_refresh:
            cached = self._read_cached_artifact(target_path, target_url)
            if cached is not None:
                data = json.loads(target_path.read_bytes().decode("utf-8"))
                return data, (cached if return_artifact else cached.sha256)

        content, last_modified = self._fetch_bytes(
            target_url, headers=headers, params=params
        )
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(content)
        sha256 = hashlib.sha256(content).hexdigest()
        fetched_at = datetime.now(UTC).isoformat()
        self._write_sidecar(
            target_path,
            url=target_url,
            sha256=sha256,
            fetched_at=fetched_at,
            last_modified=last_modified,
        )
        artifact = CachedArtifact(
            path=target_path,
            url=target_url,
            sha256=sha256,
            fetched_at=fetched_at,
            last_modified=last_modified,
            from_cache=False,
        )
        parsed = json.loads(content.decode("utf-8"))
        return parsed, (artifact if return_artifact else sha256)
