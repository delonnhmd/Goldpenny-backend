"""Tests for the FRED client (Phase 3-B-1, task 1)."""

from __future__ import annotations

import os
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx

# The client reads FRED_API_KEY at construction time. Stub it before importing
# the module under test so other tests in the suite that may import this file
# transitively don't trip the missing-key guard.
os.environ.setdefault("FRED_API_KEY", "test-key-not-real")

from app.services.realworld.fred_client import FredClient, FredObservation
from app.services.realworld.fred_series import FredSeries


CANNED_FRED_PAYLOAD = {
    "realtime_start": "2026-04-10",
    "realtime_end": "2026-04-10",
    "observation_start": "1600-01-01",
    "observation_end": "9999-12-31",
    "count": 3,
    "observations": [
        {"realtime_start": "2026-04-10", "realtime_end": "2026-04-10", "date": "2026-04-08", "value": "78.50"},
        {"realtime_start": "2026-04-10", "realtime_end": "2026-04-10", "date": "2026-04-07", "value": "."},
        {"realtime_start": "2026-04-10", "realtime_end": "2026-04-10", "date": "2026-04-06", "value": "77.10"},
    ],
}


def _make_response(status_code: int, payload: dict | None = None) -> httpx.Response:
    """Build a real httpx.Response so .json() and .raise_for_status() behave."""
    request = httpx.Request("GET", "https://api.stlouisfed.org/fred/series/observations")
    return httpx.Response(status_code=status_code, json=payload or {}, request=request)


class FredClientConstructionTests(unittest.TestCase):
    def test_missing_api_key_raises(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(RuntimeError):
                FredClient()

    def test_explicit_api_key_overrides_env(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            client = FredClient(api_key="explicit", cache_dir=Path(tmp))
            self.assertEqual(client._api_key, "explicit")

    def test_attribution_text_present(self) -> None:
        text = FredClient.attribution_text()
        self.assertIn("Federal Reserve Bank of St. Louis", text)
        self.assertIn("FRED", text)


class FredClientParsingTests(unittest.TestCase):
    def test_parses_canned_response_into_observations(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            client = FredClient(api_key="k", cache_dir=Path(tmp))
            mock_client = MagicMock()
            mock_client.__enter__.return_value.get.return_value = _make_response(200, CANNED_FRED_PAYLOAD)
            with patch("app.services.realworld.fred_client.httpx.Client", return_value=mock_client):
                rows = client.get_series(FredSeries.WTI_OIL.value, observations=3)

        self.assertEqual(len(rows), 3)
        # Sorted oldest-first.
        self.assertEqual([r.date for r in rows], [date(2026, 4, 6), date(2026, 4, 7), date(2026, 4, 8)])
        self.assertEqual(rows[0], FredObservation(series_id="DCOILWTICO", date=date(2026, 4, 6), value=77.10))
        # FRED missing-value sentinel "." becomes None.
        self.assertIsNone(rows[1].value)
        self.assertEqual(rows[2].value, 78.50)

    def test_unsupported_series_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            client = FredClient(api_key="k", cache_dir=Path(tmp))
            with self.assertRaises(ValueError):
                client.get_series("NOT_A_REAL_SERIES")


class FredClientRetryTests(unittest.TestCase):
    def test_5xx_triggers_one_retry_then_succeeds(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            client = FredClient(api_key="k", cache_dir=Path(tmp))
            mock_client = MagicMock()
            mock_client.__enter__.return_value.get.side_effect = [
                _make_response(503),
                _make_response(200, CANNED_FRED_PAYLOAD),
            ]
            with patch("app.services.realworld.fred_client.httpx.Client", return_value=mock_client):
                rows = client.get_series(FredSeries.WTI_OIL.value, observations=3)

            self.assertEqual(len(rows), 3)
            self.assertEqual(mock_client.__enter__.return_value.get.call_count, 2)

    def test_4xx_does_not_retry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            client = FredClient(api_key="k", cache_dir=Path(tmp))
            mock_client = MagicMock()
            mock_client.__enter__.return_value.get.side_effect = [
                _make_response(400),
                _make_response(200, CANNED_FRED_PAYLOAD),  # would succeed if reached
            ]
            with patch("app.services.realworld.fred_client.httpx.Client", return_value=mock_client):
                with self.assertRaises(httpx.HTTPStatusError):
                    client.get_series(FredSeries.WTI_OIL.value, observations=3)
            self.assertEqual(mock_client.__enter__.return_value.get.call_count, 1)


class FredClientCacheTests(unittest.TestCase):
    def test_cache_hit_avoids_http_call(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            client = FredClient(api_key="k", cache_dir=Path(tmp))
            mock_client = MagicMock()
            mock_client.__enter__.return_value.get.return_value = _make_response(200, CANNED_FRED_PAYLOAD)

            with patch("app.services.realworld.fred_client.httpx.Client", return_value=mock_client):
                first = client.get_series(FredSeries.WTI_OIL.value, observations=3)
                second = client.get_series(FredSeries.WTI_OIL.value, observations=3)

            self.assertEqual(first, second)
            # Only one HTTP call across both invocations.
            self.assertEqual(mock_client.__enter__.return_value.get.call_count, 1)


if __name__ == "__main__":
    unittest.main()
