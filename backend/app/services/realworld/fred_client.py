"""Read-only client for the FRED (St. Louis Fed) public data API.

Phase 3-B-1, Task 1. Sync httpx, single retry on 5xx/connection failures,
24-hour file-cache keyed on (series_id, observations).

Cache choice — file vs Postgres: file. FRED is read-only public data, the
cron path hits at most ~5 series once per day, and a JSON-on-disk cache
keeps the module self-contained (no migration, no DB session, trivial to
wipe). Durability isn't a concern: a cold cache just means one extra HTTP
call on the next run.
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

import httpx

from app.services.realworld.fred_series import SUPPORTED_SERIES_IDS

logger = logging.getLogger(__name__)


FRED_BASE_URL = "https://api.stlouisfed.org/fred/series/observations"
HTTP_TIMEOUT_SECONDS = 10.0
CACHE_TTL_SECONDS = 24 * 60 * 60
_CACHE_DIR = Path(__file__).parent / "_cache"


@dataclass(frozen=True)
class FredObservation:
    """A single observation from a FRED series.

    ``value`` is None when FRED returns its missing-value sentinel ``"."``.
    """

    series_id: str
    date: date
    value: float | None


class FredClient:
    """Sync FRED client. Construct once per process; safe to share."""

    def __init__(self, api_key: str | None = None, *, cache_dir: Path | None = None) -> None:
        key = api_key if api_key is not None else os.environ.get("FRED_API_KEY")
        if not key:
            raise RuntimeError(
                "FRED_API_KEY is not set; cannot construct FredClient. "
                "Set it in backend/.env or the process environment."
            )
        self._api_key = key
        self._cache_dir = cache_dir if cache_dir is not None else _CACHE_DIR
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def attribution_text() -> str:
        """FRED's required attribution. Surface in UI when we display values."""
        return (
            "Economic data courtesy of the Federal Reserve Bank of St. Louis "
            "(FRED®). https://fred.stlouisfed.org/"
        )

    def get_series(self, series_id: str, observations: int = 30) -> list[FredObservation]:
        """Return the most recent ``observations`` rows of ``series_id``, oldest first.

        Reads from a 24h file cache when available. On cache miss, hits FRED
        with one retry on 5xx or connection failure. 4xx is not retried.
        """
        if series_id not in SUPPORTED_SERIES_IDS:
            raise ValueError(
                f"series_id={series_id!r} is not in the supported whitelist; "
                f"add it to FredSeries before fetching."
            )
        if observations < 1:
            raise ValueError("observations must be >= 1")

        cached = self._read_cache(series_id, observations)
        if cached is not None:
            logger.debug("fred cache hit series_id=%s observations=%d", series_id, observations)
            return cached

        payload = self._fetch(series_id, observations)
        parsed = self._parse(series_id, payload)
        self._write_cache(series_id, observations, parsed)
        return parsed

    # ------------------------------------------------------------------ HTTP

    def _fetch(self, series_id: str, observations: int) -> dict[str, Any]:
        params = {
            "series_id": series_id,
            "api_key": self._api_key,
            "file_type": "json",
            "limit": observations,
            "sort_order": "desc",
        }
        attempts = 0
        while True:
            attempts += 1
            try:
                with httpx.Client(timeout=HTTP_TIMEOUT_SECONDS) as client:
                    response = client.get(FRED_BASE_URL, params=params)
            except (httpx.TimeoutException, httpx.ConnectError, httpx.RemoteProtocolError) as exc:
                if attempts < 2:
                    logger.warning("fred transient error series_id=%s attempt=%d err=%s", series_id, attempts, exc)
                    continue
                raise

            status = response.status_code
            if 500 <= status < 600:
                if attempts < 2:
                    logger.warning("fred 5xx series_id=%s status=%d attempt=%d", series_id, status, attempts)
                    continue
                response.raise_for_status()
            if 400 <= status < 500:
                response.raise_for_status()
            return response.json()

    @staticmethod
    def _parse(series_id: str, payload: dict[str, Any]) -> list[FredObservation]:
        raw = payload.get("observations") or []
        out: list[FredObservation] = []
        for row in raw:
            try:
                obs_date = datetime.strptime(row["date"], "%Y-%m-%d").date()
            except (KeyError, ValueError) as exc:
                logger.warning("fred bad date row series_id=%s row=%r err=%s", series_id, row, exc)
                continue
            raw_value = row.get("value")
            value: float | None
            if raw_value in (None, "", "."):
                value = None
            else:
                try:
                    value = float(raw_value)
                except (TypeError, ValueError):
                    logger.warning("fred bad value series_id=%s row=%r", series_id, row)
                    value = None
            out.append(FredObservation(series_id=series_id, date=obs_date, value=value))
        out.sort(key=lambda o: o.date)
        return out

    # ----------------------------------------------------------------- cache

    def _cache_path(self, series_id: str, observations: int) -> Path:
        return self._cache_dir / f"{series_id}_{observations}.json"

    def _read_cache(self, series_id: str, observations: int) -> list[FredObservation] | None:
        path = self._cache_path(series_id, observations)
        if not path.exists():
            return None
        try:
            blob = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("fred cache unreadable path=%s err=%s — refetching", path, exc)
            return None
        if time.time() - float(blob.get("fetched_at", 0)) > CACHE_TTL_SECONDS:
            return None
        try:
            return [
                FredObservation(
                    series_id=row["series_id"],
                    date=date.fromisoformat(row["date"]),
                    value=row["value"],
                )
                for row in blob["observations"]
            ]
        except (KeyError, ValueError) as exc:
            logger.warning("fred cache schema mismatch path=%s err=%s — refetching", path, exc)
            return None

    def _write_cache(self, series_id: str, observations: int, rows: list[FredObservation]) -> None:
        path = self._cache_path(series_id, observations)
        blob = {
            "fetched_at": time.time(),
            "observations": [
                {**asdict(o), "date": o.date.isoformat()} for o in rows
            ],
        }
        try:
            path.write_text(json.dumps(blob), encoding="utf-8")
        except OSError as exc:
            logger.warning("fred cache write failed path=%s err=%s", path, exc)
