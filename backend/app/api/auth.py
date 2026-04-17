import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Annotated
from uuid import UUID

from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.player import Player
from app.models.user import User
from app.services.player_onboarding_service import (
    create_survival_player_profile,
    load_existing_player_state,
)

router = APIRouter()

logger = logging.getLogger(__name__)

load_dotenv()


def _auth_error_json(
    *,
    status_code: int,
    error_code: str,
    message: str,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "success": False,
            "error_code": error_code,
            "message": message,
            "detail": message,
        },
    )

SECRET_KEY = os.getenv("SECRET_KEY", os.getenv("JWT_SECRET_KEY", "change-me"))
ALGORITHM = os.getenv("ALGORITHM", os.getenv("JWT_ALGORITHM", "HS256"))
ACCESS_TOKEN_EXPIRE_MINUTES = int(
    os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", os.getenv("JWT_EXPIRE_MINUTES", str(60 * 24 * 30)))
)
RESET_TOKEN_EXPIRE_MINUTES = int(os.getenv("RESET_TOKEN_EXPIRE_MINUTES", "15"))
RESET_URL_BASE = os.getenv("APP_RESET_URL_BASE", "goldpenny://auth/reset-password")
STARTER_REGION = "suburban"
ACTIVE_USER_STATUS = "active"

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


class RegisterRequest(BaseModel):
    email: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    token: str
    password: str


class CreatePlayerProfileRequest(BaseModel):
    display_name: str | None = None
    signup_answers: dict[str, str] | None = None


class AccountSummaryResponse(BaseModel):
    id: UUID
    email: str
    auth_provider: str
    status: str
    created_at: datetime
    last_login_at: datetime | None = None
    password_updated_at: datetime | None = None


class PlayerProfileResponse(BaseModel):
    id: UUID
    display_name: str | None = None
    gender: str | None = None
    region: str | None = None
    cash_xgp: float
    debt_xgp: float
    health: int
    stress: int
    current_job: str | None = None
    created_at: datetime | None = None
    load_ready: bool = True


class AuthSessionResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime
    account: AccountSummaryResponse
    player_profile: PlayerProfileResponse | None = None
    success: bool = True
    user_id: UUID | None = None
    email: str | None = None
    has_linked_player: bool = False


class SessionStateResponse(BaseModel):
    account: AccountSummaryResponse
    player_profile: PlayerProfileResponse | None = None


class ForgotPasswordResponse(BaseModel):
    message: str
    reset_token: str | None = None
    reset_url: str | None = None
    expires_at: datetime | None = None


class ResetPasswordResponse(BaseModel):
    message: str


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime | None) -> datetime:
    if value is None:
        return _utc_now()
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _normalize_email(value: str) -> str:
    email = str(value or "").strip().lower()
    if not email or "@" not in email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Enter a valid email address.",
        )
    return email


def _validate_password(value: str) -> str:
    password = str(value or "")
    if len(password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 8 characters long.",
        )
    return password


def _player_display_name_from_email(email: str) -> str:
    local_part = email.split("@", 1)[0]
    normalized = local_part.replace(".", " ").replace("_", " ").replace("-", " ").strip()
    if not normalized:
        return "Gold Penny Player"
    return normalized[:80]


def _password_version(user: User) -> int:
    source = user.password_updated_at or user.created_at or _utc_now()
    return int(_as_utc(source).timestamp())


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def _create_token(
    *,
    subject: str,
    purpose: str,
    expires_in_minutes: int,
    password_version: int,
) -> tuple[str, datetime]:
    issued_at = _utc_now()
    expires_at = issued_at + timedelta(minutes=max(1, int(expires_in_minutes)))
    payload = {
        "sub": subject,
        "type": purpose,
        "pwd_v": password_version,
        "iat": issued_at,
        "exp": expires_at,
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM), expires_at


def create_access_token(user: User) -> tuple[str, datetime]:
    return _create_token(
        subject=str(user.id),
        purpose="access",
        expires_in_minutes=ACCESS_TOKEN_EXPIRE_MINUTES,
        password_version=_password_version(user),
    )


def create_reset_token(user: User) -> tuple[str, datetime]:
    return _create_token(
        subject=str(user.id),
        purpose="password_reset",
        expires_in_minutes=RESET_TOKEN_EXPIRE_MINUTES,
        password_version=_password_version(user),
    )


def _decode_token(token: str, *, expected_purpose: str) -> tuple[UUID, int]:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED if expected_purpose == "access" else status.HTTP_400_BAD_REQUEST,
        detail="Invalid or expired token." if expected_purpose == "access" else "Invalid or expired reset token.",
        headers={"WWW-Authenticate": "Bearer"} if expected_purpose == "access" else None,
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        token_type = str(payload.get("type") or "").strip().lower()
        password_version = int(payload.get("pwd_v") or 0)
        if not user_id or token_type != expected_purpose:
            raise unauthorized
        return UUID(str(user_id)), password_version
    except (JWTError, ValueError, TypeError):
        raise unauthorized


def _bootstrap_clean_player_profile(
    db: Session,
    user: User,
    *,
    display_name: str | None = None,
    signup_answers: dict[str, str] | None = None,
) -> Player:
    resolved_display_name = str(display_name or "").strip() or _player_display_name_from_email(user.email)
    return create_survival_player_profile(
        db,
        user_id=user.id,
        display_name=resolved_display_name,
        fallback_email=user.email,
        region=STARTER_REGION,
        questionnaire_answers=signup_answers,
        daily_state_note="fresh_start_profile_created",
    )


def get_user_player_profile(db: Session, user: User) -> Player | None:
    return db.query(Player).filter(Player.user_id == str(user.id)).first()


def _build_account_payload(user: User) -> AccountSummaryResponse:
    return AccountSummaryResponse(
        id=user.id,
        email=user.email,
        auth_provider=str(user.auth_provider or "password"),
        status=str(user.status or ACTIVE_USER_STATUS),
        created_at=_as_utc(user.created_at),
        last_login_at=_as_utc(user.last_login_at) if user.last_login_at is not None else None,
        password_updated_at=_as_utc(user.password_updated_at) if user.password_updated_at is not None else None,
    )


def _build_player_profile_payload(db: Session, player: Player) -> PlayerProfileResponse:
    try:
        payload = load_existing_player_state(db, player.id)
    except Exception:
        payload = {}

    employment = payload.get("active_employment_summary") if isinstance(payload, dict) else {}
    current_job = None
    if isinstance(employment, dict):
        current_job = str(employment.get("current_job_code") or "").strip() or None
    if not current_job:
        current_job = str(getattr(player, "main_job", "") or "").strip() or None

    return PlayerProfileResponse(
        id=player.id,
        display_name=str(payload.get("display_name")) if isinstance(payload, dict) and payload.get("display_name") is not None else player.display_name,
        gender=str(payload.get("gender")) if isinstance(payload, dict) and payload.get("gender") is not None else player.gender,
        region=str(payload.get("region")) if isinstance(payload, dict) and payload.get("region") is not None else str(player.region or STARTER_REGION),
        cash_xgp=float(payload.get("cash_xgp")) if isinstance(payload, dict) and payload.get("cash_xgp") is not None else float(player.cash),
        debt_xgp=float(payload.get("debt_xgp")) if isinstance(payload, dict) and payload.get("debt_xgp") is not None else float(player.debt_xgp),
        health=int(payload.get("health")) if isinstance(payload, dict) and payload.get("health") is not None else int(player.health or 100),
        stress=int(payload.get("stress")) if isinstance(payload, dict) and payload.get("stress") is not None else int(player.stress or 0),
        current_job=current_job,
        created_at=_as_utc(player.created_at) if player.created_at is not None else None,
        load_ready=bool(payload.get("load_ready", True)) if isinstance(payload, dict) else True,
    )


def _build_session_state(db: Session, user: User) -> tuple[AccountSummaryResponse, PlayerProfileResponse | None]:
    if str(user.status or ACTIVE_USER_STATUS).strip().lower() != ACTIVE_USER_STATUS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account is not active.",
        )

    player = get_user_player_profile(db, user)
    player_profile = _build_player_profile_payload(db, player) if player is not None else None
    return _build_account_payload(user), player_profile


def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Session = Depends(get_db),
) -> User:
    user_uuid, password_version = _decode_token(token, expected_purpose="access")
    user = db.query(User).filter(User.id == user_uuid).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if str(user.status or ACTIVE_USER_STATUS).strip().lower() != ACTIVE_USER_STATUS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account is not active.",
        )
    if password_version != _password_version(user):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    # Normalize + validate first so we emit structured 400s before touching the DB.
    try:
        email = _normalize_email(payload.email)
        password = _validate_password(payload.password)
    except HTTPException:
        # Let the global HTTP handler format the JSON body.
        raise

    log_ctx = {"email": email, "stage": "start"}
    logger.info("auth_register_attempt", extra=log_ctx)

    # Pre-check for duplicate email. Uniqueness is also enforced at the DB level.
    try:
        existing = db.query(User).filter(User.email == email).first()
    except Exception as exc:
        logger.exception("auth_register_email_lookup_failed", extra={**log_ctx, "error_type": type(exc).__name__})
        return _auth_error_json(
            status_code=500,
            error_code="internal_register_error",
            message="Could not create account right now. Please try again.",
        )

    if existing is not None:
        logger.info("auth_register_duplicate_email", extra={**log_ctx, "stage": "duplicate"})
        return _auth_error_json(
            status_code=400,
            error_code="email_already_exists",
            message="That email is already registered. Try logging in.",
        )

    # Account creation only — a linked player profile is created later via
    # /auth/player-profile from a controlled post-login flow. Keeping register
    # isolated from gameplay state bugs is intentional.
    now = _utc_now()
    try:
        hashed = get_password_hash(password)
    except Exception as exc:
        logger.exception("auth_register_password_hash_failed", extra={**log_ctx, "error_type": type(exc).__name__})
        return _auth_error_json(
            status_code=500,
            error_code="password_hash_failed",
            message="Could not create account right now. Please try again.",
        )

    try:
        user = User(
            email=email,
            auth_provider="password",
            hashed_password=hashed,
            status=ACTIVE_USER_STATUS,
            last_login_at=now,
            password_updated_at=now,
        )
        db.add(user)
        db.flush()
        db.commit()
        db.refresh(user)
    except IntegrityError as exc:
        db.rollback()
        logger.info("auth_register_integrity_error", extra={**log_ctx, "stage": "insert", "error_type": type(exc).__name__})
        return _auth_error_json(
            status_code=400,
            error_code="email_already_exists",
            message="That email is already registered. Try logging in.",
        )
    except Exception as exc:
        db.rollback()
        logger.exception("auth_register_insert_failed", extra={**log_ctx, "stage": "insert", "error_type": type(exc).__name__})
        return _auth_error_json(
            status_code=500,
            error_code="internal_register_error",
            message="Could not create account right now. Please try again.",
        )

    try:
        access_token, expires_at = create_access_token(user)
        account, player_profile = _build_session_state(db, user)
    except Exception as exc:
        logger.exception("auth_register_session_build_failed", extra={**log_ctx, "stage": "session", "error_type": type(exc).__name__})
        return _auth_error_json(
            status_code=500,
            error_code="session_build_failed",
            message="Account created but session could not start. Please log in.",
        )

    logger.info("auth_register_success", extra={**log_ctx, "stage": "complete", "user_id": str(user.id)})
    return AuthSessionResponse(
        access_token=access_token,
        expires_at=expires_at,
        account=account,
        player_profile=player_profile,
        success=True,
        user_id=user.id,
        email=user.email,
        has_linked_player=player_profile is not None,
    )


@router.post("/login", response_model=AuthSessionResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> AuthSessionResponse:
    email = _normalize_email(payload.email)
    user = db.query(User).filter(User.email == email).first()
    if user is None or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if str(user.status or ACTIVE_USER_STATUS).strip().lower() != ACTIVE_USER_STATUS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account is not active.",
        )

    try:
        user.last_login_at = _utc_now()
        db.commit()
        db.refresh(user)
    except Exception:
        db.rollback()
        raise

    access_token, expires_at = create_access_token(user)
    account, player_profile = _build_session_state(db, user)
    return AuthSessionResponse(
        access_token=access_token,
        expires_at=expires_at,
        account=account,
        player_profile=player_profile,
    )


@router.get("/session", response_model=SessionStateResponse)
def get_session_state(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SessionStateResponse:
    account, player_profile = _build_session_state(db, current_user)
    return SessionStateResponse(account=account, player_profile=player_profile)


@router.post("/player-profile", response_model=SessionStateResponse, status_code=status.HTTP_201_CREATED)
def create_player_profile(
    payload: CreatePlayerProfileRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SessionStateResponse:
    existing = get_user_player_profile(db, current_user)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This account already has a linked player profile.",
        )

    try:
        player = _bootstrap_clean_player_profile(
            db,
            current_user,
            display_name=payload.display_name,
            signup_answers=payload.signup_answers,
        )
        db.commit()
        db.refresh(current_user)
        db.refresh(player)
    except Exception:
        db.rollback()
        raise

    account, player_profile = _build_session_state(db, current_user)
    return SessionStateResponse(account=account, player_profile=player_profile)


@router.post("/forgot-password", response_model=ForgotPasswordResponse)
def forgot_password(payload: ForgotPasswordRequest, db: Session = Depends(get_db)) -> ForgotPasswordResponse:
    email = _normalize_email(payload.email)
    user = db.query(User).filter(User.email == email).first()
    message = "If that email exists, a password reset link is ready."

    if user is None or str(user.status or ACTIVE_USER_STATUS).strip().lower() != ACTIVE_USER_STATUS:
        return ForgotPasswordResponse(message=message)

    reset_token, expires_at = create_reset_token(user)
    joiner = "&" if "?" in RESET_URL_BASE else "?"
    reset_url = f"{RESET_URL_BASE}{joiner}token={reset_token}"
    return ForgotPasswordResponse(
        message=message,
        reset_token=reset_token,
        reset_url=reset_url,
        expires_at=expires_at,
    )


@router.post("/reset-password", response_model=ResetPasswordResponse)
def reset_password(payload: ResetPasswordRequest, db: Session = Depends(get_db)) -> ResetPasswordResponse:
    new_password = _validate_password(payload.password)
    user_uuid, password_version = _decode_token(payload.token, expected_purpose="password_reset")

    user = db.query(User).filter(User.id == user_uuid).first()
    if user is None or str(user.status or ACTIVE_USER_STATUS).strip().lower() != ACTIVE_USER_STATUS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token.",
        )
    if password_version != _password_version(user):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token.",
        )

    user.hashed_password = get_password_hash(new_password)
    user.password_updated_at = _utc_now()
    db.commit()
    return ResetPasswordResponse(message="Password updated successfully. Please log in again.")
