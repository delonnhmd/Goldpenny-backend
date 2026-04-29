from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.player import Player
from app.models.player_push_token import PlayerPushToken
from app.services.notification_service import send_push_notification


router = APIRouter()

SUPPORTED_PLATFORMS = {"ios", "android", "unknown"}


class RegisterPushTokenRequest(BaseModel):
    player_id: str = Field(..., min_length=1)
    push_token: str = Field(..., min_length=1, max_length=255)
    platform: Optional[str] = Field(default=None, max_length=20)


class RegisterPushTokenResponse(BaseModel):
    ok: bool
    token_id: str
    player_id: str
    platform: str


class TestPushRequest(BaseModel):
    player_id: str = Field(..., min_length=1)
    title: str = Field("Test", min_length=1, max_length=80)
    body: str = Field("Push is working", min_length=1, max_length=180)
    data: dict[str, Any] | None = None


class PushSendResponse(BaseModel):
    ok: bool
    player_id: str
    tokens: int
    sent: int
    failed: int
    tickets: list[dict[str, Any]] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    message: str | None = None


def _parse_player_id(player_id: str) -> UUID:
    try:
        return UUID(str(player_id))
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid player_id.",
        ) from None


def _normalize_platform(platform: str | None) -> str:
    value = str(platform or "unknown").strip().lower()
    return value if value in SUPPORTED_PLATFORMS else "unknown"


@router.post(
    "/register-token",
    response_model=RegisterPushTokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register an Expo push token for a player",
)
def register_token(payload: RegisterPushTokenRequest, db: Session = Depends(get_db)) -> RegisterPushTokenResponse:
    player_uuid = _parse_player_id(payload.player_id)
    player = db.query(Player).filter(Player.id == player_uuid).first()
    if player is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Player not found.",
        )

    push_token = payload.push_token.strip()
    platform = _normalize_platform(payload.platform)

    existing = db.query(PlayerPushToken).filter(PlayerPushToken.push_token == push_token).first()
    if existing:
        existing.player_id = player.id
        existing.platform = platform
        row = existing
    else:
        row = PlayerPushToken(
            player_id=player.id,
            push_token=push_token,
            platform=platform,
        )
        db.add(row)

    db.commit()
    db.refresh(row)

    return RegisterPushTokenResponse(
        ok=True,
        token_id=str(row.id),
        player_id=str(row.player_id),
        platform=row.platform,
    )


@router.post(
    "/test",
    response_model=PushSendResponse,
    summary="Send a test push notification to a player's registered devices",
)
def send_test_push(payload: TestPushRequest, db: Session = Depends(get_db)) -> PushSendResponse:
    player_uuid = _parse_player_id(payload.player_id)
    player = db.query(Player).filter(Player.id == player_uuid).first()
    if player is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Player not found.",
        )

    result = send_push_notification(
        str(player.id),
        payload.title,
        payload.body,
        data=payload.data or {"kind": "push_test"},
        db=db,
    )
    return PushSendResponse(player_id=str(player.id), **result)
