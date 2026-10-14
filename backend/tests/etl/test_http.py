"""Unit tests for the resilient HTTP client, disk cache, and rate limiter."""

import hashlib
from pathlib import Path

from pytest_mock import MockerFixture

from territorio.etl.http import CachedHttpClient, TokenBucketRateLimiter


def test_token_bucket_rate_limiter_sleeps_when_interval_not_elapsed(
    mocker: MockerFixture,
) -> None:
    """Verifies that the rate limiter enforces minimum spacing between requests.

    Args:
        mocker: Pytest-mock fixture used to stub monotonic clock and sleep.
    """
    mock_sleep = mocker.patch("time.sleep")
    mocker.patch("time.monotonic", side_effect=[100.0, 100.1, 100.6])

    limiter = TokenBucketRateLimiter(rate_per_min=120)  # 0.5s interval
    limiter.acquire()
    limiter.acquire()

    mock_sleep.assert_called_once()
    slept = mock_sleep.call_args.args[0]
    assert abs(slept - 0.4) < 1e-6


def test_cached_http_client_downloads_and_reuses_disk_cache(
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    """Verifies that `download` writes content + SHA-256 metadata and reuses cache.

    Args:
        tmp_path: Temporary directory provided by pytest.
        mocker: Pytest-mock fixture used to stub httpx streaming responses.
    """
    payload = b"codigo_tse;codigo_ibge\n73709;5101837\n"
    expected_sha = hashlib.sha256(payload).hexdigest()

    fake_response = mocker.MagicMock()
    fake_response.status_code = 200
    fake_response.headers = {"Last-Modified": "Fri, 09 Oct 2026 19:32:00 GMT"}
    fake_response.iter_bytes.return_value = [payload]
    fake_response.raise_for_status.return_value = None

    stream_ctx = mocker.MagicMock()
    stream_ctx.__enter__.return_value = fake_response
    stream_ctx.__exit__.return_value = False

    client = CachedHttpClient(cache_root=tmp_path, timeout_s=10.0)
    mock_stream = mocker.patch.object(client._client, "stream", return_value=stream_ctx)

    artifact1 = client.download(
        source="tse",
        url="https://cdn.tse.jus.br/test.zip",
        filename="test.zip",
    )
    assert artifact1.path.exists()
    assert artifact1.sha256 == expected_sha
    assert artifact1.from_cache is False
    assert artifact1.last_modified == "Fri, 09 Oct 2026 19:32:00 GMT"
    assert mock_stream.call_count == 1

    # Second call without force_refresh must hit disk cache without network I/O
    artifact2 = client.download(
        source="tse",
        url="https://cdn.tse.jus.br/test.zip",
        filename="test.zip",
    )
    assert artifact2.path == artifact1.path
    assert artifact2.sha256 == expected_sha
    assert artifact2.from_cache is True
    assert mock_stream.call_count == 1
    client.close()


def test_cached_http_client_get_json_uses_headers_and_cache(
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    """Verifies JSON fetching, custom headers, and local caching.

    Args:
        tmp_path: Temporary directory provided by pytest.
        mocker: Pytest-mock fixture.
    """
    fake_resp = mocker.Mock()
    fake_resp.status_code = 200
    fake_resp.content = b'[{"V": "100"}]'
    fake_resp.headers = {}
    fake_resp.raise_for_status.return_value = None

    client = CachedHttpClient(cache_root=tmp_path, timeout_s=10.0)
    mock_get = mocker.patch.object(client._client, "get", return_value=fake_resp)

    data, artifact = client.get_json(
        source="sidra",
        url="https://apisidra.ibge.gov.br/values/t/4709",
        cache_key="t4709.json",
        headers={"X-Custom": "1"},
    )
    assert data == [{"V": "100"}]
    assert artifact.from_cache is False
    mock_get.assert_called_once()
    assert mock_get.call_args.kwargs["headers"]["X-Custom"] == "1"

    # Cached call
    data_cached, artifact_cached = client.get_json(
        source="sidra",
        url="https://apisidra.ibge.gov.br/values/t/4709",
        cache_key="t4709.json",
    )
    assert data_cached == [{"V": "100"}]
    assert artifact_cached.from_cache is True
    assert mock_get.call_count == 1
    client.close()
