import secrets

import pytest

from app.core.security import load_jwt_secret


def test_load_jwt_secret_raises_when_missing(monkeypatch):
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)

    with pytest.raises(RuntimeError, match="SECRET_KEY is required"):
        load_jwt_secret()

def test_load_jwt_secret_raises_on_known_weak_defaults(monkeypatch):
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)

    for weak_secret in ("change-me", "changeme", "secret"):
        monkeypatch.setenv("SECRET_KEY", weak_secret)
        with pytest.raises(RuntimeError, match="known weak default"):
            load_jwt_secret()


def test_load_jwt_secret_raises_when_too_short(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "a" * 16)
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)

    with pytest.raises(RuntimeError, match="too short"):
        load_jwt_secret()


def test_load_jwt_secret_returns_value_when_strong(monkeypatch):
    strong_secret = secrets.token_urlsafe(48)
    monkeypatch.setenv("SECRET_KEY", strong_secret)
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)

    assert load_jwt_secret() == strong_secret


def test_load_jwt_secret_falls_back_to_jwt_secret_key(monkeypatch):
    legacy_secret = secrets.token_urlsafe(48)
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.setenv("JWT_SECRET_KEY", legacy_secret)

    assert load_jwt_secret() == legacy_secret
