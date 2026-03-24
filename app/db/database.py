import os
import logging
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
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


def _infer_supabase_project_ref() -> str | None:
    parsed = urlparse(DATABASE_URL)
    host = parsed.hostname or ""
    username = parsed.username or ""

    # direct db host: db.<project-ref>.supabase.co
    if host.startswith("db.") and ".supabase.co" in host:
        parts = host.split(".")
        if len(parts) >= 3:
            return parts[1]

    # pooler username pattern: postgres.<project-ref>
    if username.startswith("postgres.") and len(username.split(".", 1)) == 2:
        return username.split(".", 1)[1]

    return None


def log_database_schema_diagnostics() -> None:
    """Emit one-time safe DB target + schema diagnostics for production triage."""
    parsed = urlparse(DATABASE_URL)
    db_host = parsed.hostname or "(missing)"
    db_name = parsed.path.lstrip("/") or "(missing)"
    project_ref = _infer_supabase_project_ref() or "(unknown)"

    logger.info(
        "DB target diagnostics: host=%s db=%s project_ref=%s",
        db_host,
        db_name,
        project_ref,
    )

    try:
        with engine.connect() as conn:
            current_database = conn.execute(text("SELECT current_database()")).scalar()
            current_schema = conn.execute(text("SELECT current_schema()")).scalar()
            search_path = conn.execute(text("SHOW search_path")).scalar()

            player_tables_rows = conn.execute(
                text(
                    """
                    SELECT table_schema
                    FROM information_schema.tables
                    WHERE table_name = 'players'
                    ORDER BY table_schema
                    """
                )
            ).fetchall()
            player_table_schemas = [str(row[0]) for row in player_tables_rows]

            gender_column_rows = conn.execute(
                text(
                    """
                    SELECT table_schema
                    FROM information_schema.columns
                    WHERE table_name = 'players' AND column_name = 'gender'
                    ORDER BY table_schema
                    """
                )
            ).fetchall()
            gender_column_schemas = [str(row[0]) for row in gender_column_rows]

            logger.info(
                "DB schema diagnostics: current_database=%s current_schema=%s search_path=%s "
                "players_table_schemas=%s players_gender_column_schemas=%s",
                current_database or "(unknown)",
                current_schema or "(unknown)",
                search_path or "(unknown)",
                player_table_schemas or [],
                gender_column_schemas or [],
            )
    except Exception as exc:
        logger.warning("DB schema diagnostics query failed: %s", str(exc))


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
