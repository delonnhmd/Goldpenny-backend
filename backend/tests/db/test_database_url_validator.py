"""Validator tests for DATABASE_URL.

The validator must allow sqlite URLs (so the test harness can stand up an
in-memory DB) and must keep rejecting genuinely unsupported schemes in
production environments.
"""

from __future__ import annotations

import os

# Pre-set DATABASE_URL before importing database.py — its module-level call
# to the validator would otherwise trip on whatever's in backend/.env.
# load_dotenv runs with override=False, so this value sticks.
os.environ["DATABASE_URL"] = "postgresql://test:test@localhost:5432/test_db"

import pytest

from app.db.database import _validate_and_enrich_database_url


SQLITE_FILE = "sqlite:///./test_validator.db"
SQLITE_MEMORY = "sqlite:///:memory:"
POSTGRES = "postgresql://user:pass@localhost:5432/test_db"
MYSQL = "mysql://user:pass@localhost:3306/test_db"


def test_sqlite_file_url_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    assert _validate_and_enrich_database_url(SQLITE_FILE) == SQLITE_FILE


def test_sqlite_memory_url_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    assert _validate_and_enrich_database_url(SQLITE_MEMORY) == SQLITE_MEMORY


def test_postgres_url_still_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    enriched = _validate_and_enrich_database_url(POSTGRES)
    # Validator may rewrite (e.g. adding sslmode for supabase hosts) but
    # localhost is left alone, so we get the original back.
    assert enriched == POSTGRES


def test_unsupported_scheme_rejected_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    with pytest.raises(ValueError, match="unsupported scheme"):
        _validate_and_enrich_database_url(MYSQL)


def test_environment_test_bypasses_validator(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "test")
    # Even an otherwise-rejected URL passes through when ENVIRONMENT=test.
    assert _validate_and_enrich_database_url(MYSQL) == MYSQL
