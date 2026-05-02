from __future__ import annotations

from fastapi import APIRouter

from app.services.game_time_service import get_game_time_payload

router = APIRouter()


@router.get("/game-time", summary="Current server-owned game timer metadata")
def get_game_time() -> dict:
    return get_game_time_payload()
