"""Canonical job-key helpers for gameplay-facing employment flows."""

from __future__ import annotations

from typing import Final

CANONICAL_MAIN_JOB_KEYS: Final[tuple[str, ...]] = (
    "auto_mechanic",
    "aircraft_mechanic",
    "banker",
    "chef",
    "cleaner",
    "warehouse_operator",
    "real_estate_agent",
    "retail",
    "delivery",
)
CANONICAL_MAIN_JOB_KEY_SET: Final[frozenset[str]] = frozenset(CANONICAL_MAIN_JOB_KEYS)
CANONICAL_SIDE_JOB_KEYS: Final[frozenset[str]] = frozenset({"rideshare"})
LEGACY_JOB_KEY_ALIASES: Final[dict[str, str]] = {
    "retail_worker": "retail",
    "delivery_driver": "delivery",
    "warehouse_worker": "warehouse_operator",
    "real_estate": "real_estate_agent",
}


def supported_main_job_keys_text() -> str:
    return ", ".join(CANONICAL_MAIN_JOB_KEYS)


def normalize_job_key(
    value: object,
    *,
    allow_aliases: bool = True,
    allow_side_jobs: bool = True,
) -> str | None:
    key = str(value or "").strip().lower()
    if not key:
        return None
    if allow_aliases:
        key = LEGACY_JOB_KEY_ALIASES.get(key, key)
    if key in CANONICAL_MAIN_JOB_KEY_SET:
        return key
    if allow_side_jobs and key in CANONICAL_SIDE_JOB_KEYS:
        return key
    return None


def normalize_main_job_key(value: object, *, allow_aliases: bool = True) -> str | None:
    return normalize_job_key(value, allow_aliases=allow_aliases, allow_side_jobs=False)


def job_key_lookup_variants(
    value: object,
    *,
    allow_side_jobs: bool = True,
) -> tuple[str, ...]:
    normalized = normalize_job_key(value, allow_aliases=True, allow_side_jobs=allow_side_jobs)
    if normalized is None:
        return tuple()
    variants = [normalized]
    for legacy_key, canonical_key in LEGACY_JOB_KEY_ALIASES.items():
        if canonical_key == normalized:
            variants.append(legacy_key)
    return tuple(dict.fromkeys(variants))


def require_canonical_main_job_key(value: object) -> str:
    normalized = normalize_main_job_key(value, allow_aliases=False)
    if normalized is not None:
        return normalized
    provided = str(value or "").strip() or "<empty>"
    raise ValueError(
        f"Invalid job key: {provided}. Expected one of: {supported_main_job_keys_text()}"
    )
