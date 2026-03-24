import os
import logging
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# Load environment variables from the project root `.env` file.
load_dotenv()

logger = logging.getLogger("goldpenny.database")


def _normalize_database_url(raw_value: str | None) -> str:
    if not raw_value:
        raise ValueError("DATABASE_URL is not set in environment variables. Add it to .env.")

    value = raw_value.strip().strip('"').strip("'")
    if value.lower().startswith("uri:"):
        # Common copy/paste mistake from dashboards/documentation snippets.
        value = value[4:].strip()
    if value.startswith("postgres://"):
        # SQLAlchemy v2-compatible alias.
        value = f"postgresql://{value[len('postgres://'):]}"
    return value


def _validate_and_enrich_database_url(database_url: str) -> str:
    parsed = urlparse(database_url)
    scheme = (parsed.scheme or "").lower()
    if not scheme:
        raise ValueError(
            "DATABASE_URL is malformed: missing URI scheme. Expected "
            "'postgresql://user:password@host:5432/dbname'."
        )
    if not (scheme.startswith("postgresql") or scheme.startswith("postgres")):
        raise ValueError(
            f"DATABASE_URL uses unsupported scheme '{parsed.scheme}'. "
            "Expected a PostgreSQL URI."
        )

    host = parsed.hostname or ""
    db_name = parsed.path.lstrip("/") or "(missing)"

    logger.info(
        "Database URL diagnostics: scheme=%s host=%s port=%s db=%s",
        parsed.scheme,
        host or "(missing)",
        parsed.port or "(default)",
        db_name,
    )

    if "@@" in database_url.split("?", 1)[0]:
        raise ValueError(
            "DATABASE_URL appears malformed (found '@@'). If your password "
            "contains '@', URL-encode it as '%40'."
        )

    if not host:
        raise ValueError(
            "DATABASE_URL is malformed: host is missing. "
            "Expected host like 'aws-0-us-west-2.pooler.supabase.com'."
        )
    if host.startswith("@") or host.startswith("/"):
        raise ValueError(
            f"DATABASE_URL host is invalid ('{host}'). This can cause socket-path "
            "connection errors. Ensure a full TCP URI format is used."
        )
    if ".s.PGSQL." in host:
        raise ValueError(
            f"DATABASE_URL host looks like a socket path ('{host}'). "
            "Use a normal PostgreSQL host name instead."
        )

    # Supabase pooler/direct connections should use SSL in hosted environments.
    if "supabase.com" in host and "sslmode=" not in parsed.query.lower():
        query_pairs = parse_qsl(parsed.query, keep_blank_values=True)
        query_pairs.append(("sslmode", "require"))
        parsed = parsed._replace(query=urlencode(query_pairs))
        database_url = urlunparse(parsed)
        logger.info("Database URL diagnostics: appended sslmode=require for Supabase host=%s", host)

    return database_url


DATABASE_URL = _validate_and_enrich_database_url(
    _normalize_database_url(os.getenv("DATABASE_URL"))
)

engine = create_engine(DATABASE_URL, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, future=True)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
