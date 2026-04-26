import os


_WEAK_JWT_SECRETS = {
    "change" + "-me",
    "change" + "me",
    "secret",
    "dev",
    "test",
}


def load_jwt_secret() -> str:
    secret = os.getenv("SECRET_KEY")
    if secret is None or not secret.strip():
        secret = os.getenv("JWT_SECRET_KEY")

    secret = "" if secret is None else str(secret).strip()
    if not secret:
        raise RuntimeError(
            "SECRET_KEY is required. Set SECRET_KEY to a cryptographically random value "
            "with at least 32 characters."
        )

    if secret.lower() in _WEAK_JWT_SECRETS:
        raise RuntimeError(
            "SECRET_KEY is using a known weak default. Set SECRET_KEY to a cryptographically "
            "random value with at least 32 characters."
        )

    if len(secret) < 32:
        raise RuntimeError(
            "SECRET_KEY is too short. Set SECRET_KEY to a cryptographically random value "
            "with at least 32 characters."
        )

    return secret
