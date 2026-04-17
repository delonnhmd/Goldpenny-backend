"""Deals API — Step 13: Co-op Deals System.

Route overview
--------------
GET  /deals/templates          — List all active deal templates (public)
GET  /deals/open               — Browse currently open deals (public)
POST /deals/create             — Authenticated: host a new co-op deal
POST /deals/join               — Authenticated: join an open deal
POST /deals/complete           — Admin/internal: complete a filled deal
GET  /deals/my                 — Authenticated: personal deal profile summary
GET  /deals/history            — Authenticated: full participation/payout history
POST /deals/admin/expire       — Admin/internal: expire stale open deals

Economic design:
  Co-op deals are structured collaboration windows.  Players fill roles using
  their jobs or businesses — no freeform contracts, no negotiation.

  Fixed split presets are enforced at deal creation; the host picks one of the
  template's allowed presets and all participants are bound to it.

  Payout is atomic: complete_coop_deal() either pays everyone or rolls back.
  Contribution events and XGP ledger entries are written on every completion.
"""

from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.db.database import get_db
from app.engine.coop_deal_engine import (
    build_deals_summary,
    complete_coop_deal,
    create_coop_deal,
    expire_open_deals,
    get_or_seed_default_deal_templates,
    join_coop_deal,
)
from app.models.coop_deal import CoopDeal
from app.models.coop_deal_participant import CoopDealParticipant
from app.models.coop_deal_payout import CoopDealPayout
from app.models.deal_template import DealTemplate
from app.models.game_state import GameState
from app.models.player import Player
from app.models.user import User

router = APIRouter()


# ── Internal helpers ──────────────────────────────────────────────────────────


def _get_player_or_404(user: User, db: Session) -> Player:
    player = db.query(Player).filter(Player.user_id == str(user.id)).first()
    if player is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Player profile not found.",
        )
    return player


def _current_day(db: Session) -> int:
    state = db.query(GameState).order_by(GameState.id.asc()).first()
    return int(state.current_day) if state else 1


# ── Request bodies ────────────────────────────────────────────────────────────


class CreateDealRequest(BaseModel):
    template_id: str = Field(..., description="Template ID for the deal to create")
    split_preset: list[float] = Field(
        ...,
        description=(
            "Split percentages matching the template's required role count. "
            "Must be one of template.allowed_split_presets and sum to 100."
        ),
    )


class JoinDealRequest(BaseModel):
    deal_id: int = Field(..., description="Integer ID of the open deal to join")


class CompleteDealRequest(BaseModel):
    deal_id: int = Field(..., description="Integer ID of the filled deal to complete")


class ExpireDealsRequest(BaseModel):
    day_number: int = Field(
        ...,
        description="Expire all open deals with expires_day_number <= this value",
    )


# ── Routes ────────────────────────────────────────────────────────────────────


@router.get("/templates")
def get_deal_templates(db: Session = Depends(get_db)) -> list[dict]:
    """Return all active co-op deal templates.

    Templates are system-generated and seeded at startup.  They define which
    roles, split presets, and base payouts are available.

    Public endpoint — no authentication required.
    """
    templates = (
        db.query(DealTemplate)
        .filter(DealTemplate.is_active.is_(True))
        .order_by(DealTemplate.id.asc())
        .all()
    )
    return [
        {
            "template_id": t.template_id,
            "display_name": t.display_name,
            "description": t.description,
            "required_roles": json.loads(t.required_roles_json),
            "allowed_split_presets": json.loads(t.allowed_split_presets_json),
            "base_payout_xgp": float(t.base_payout_xgp),
            "hours_required_per_participant": t.hours_required_per_participant,
            "region_bias": t.region_bias,
            "confidence_sensitivity": t.confidence_sensitivity,
            "basket_dependency": (
                json.loads(t.basket_dependency_json)
                if t.basket_dependency_json
                else None
            ),
            "expires_behavior": "Deals expire after 1 in-game day if unfilled.",
        }
        for t in templates
    ]


@router.get("/open")
def get_open_deals(
    limit: int = Query(50, ge=1, le=200, description="Max open deals to return"),
    db: Session = Depends(get_db),
) -> list[dict]:
    """Return currently open co-op deals accepting new participants.

    Excludes deals that have already expired based on the current game day.
    Each row shows which roles are filled and which remain open.

    Public endpoint — no authentication required.
    """
    current_day = _current_day(db)
    deals = (
        db.query(CoopDeal)
        .filter(
            CoopDeal.status == "open",
            CoopDeal.expires_day_number > current_day,
        )
        .order_by(CoopDeal.created_at.desc())
        .limit(limit)
        .all()
    )

    result = []
    for deal in deals:
        participants = (
            db.query(CoopDealParticipant)
            .filter(CoopDealParticipant.deal_id == deal.id)
            .all()
        )
        required_roles: list[str] = json.loads(deal.required_roles_json)
        filled_roles: set[str] = {p.role_id for p in participants}

        result.append({
            "deal_id": deal.id,
            "template_id": deal.template_id,
            "display_name": deal.display_name,
            "host_player_id": deal.host_player_id,
            "status": deal.status,
            "required_roles": required_roles,
            "roles_filled": sorted(filled_roles),
            "roles_remaining": [r for r in required_roles if r not in filled_roles],
            "assigned_split": json.loads(deal.assigned_split_json),
            "base_payout_xgp": float(deal.base_payout_xgp),
            "participant_count": len(participants),
            "region_bias": deal.region_bias,
            "created_day_number": deal.created_day_number,
            "expires_day_number": deal.expires_day_number,
        })

    return result


@router.post("/create")
def create_deal(
    body: CreateDealRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Host a new co-op deal from a system template.

    The authenticated player becomes the host and is automatically assigned
    to the first required role they qualify for.

    The split_preset must be one of the template's allowed_split_presets and
    must match the number of required roles.

    The deal expires in 1 in-game day if not fully filled.
    The host is not paid until the deal is completed.
    """
    player = _get_player_or_404(current_user, db)
    try:
        return create_coop_deal(
            db=db,
            host_player=player,
            template_id=body.template_id,
            split_preset=body.split_preset,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post("/join")
def join_deal(
    body: JoinDealRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Join an open co-op deal.

    The authenticated player is automatically assigned to whichever unfilled
    role they qualify for.  If all roles are filled after this join, the deal
    transitions to 'filled' status automatically.

    A player may not join the same deal twice.
    A player can only fill one role per deal.
    """
    player = _get_player_or_404(current_user, db)
    try:
        return join_coop_deal(db=db, player=player, deal_id=body.deal_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post("/complete")
def complete_deal(
    body: CompleteDealRequest,
    db: Session = Depends(get_db),
) -> dict:
    """Complete a fully filled co-op deal and distribute XGP payout.

    Only deals with status 'filled' can be completed.  Payout is atomic — all
    participants are paid or nothing changes (full rollback on failure).

    For each participant:
    - XGP credited proportional to their split_percent.
    - CoopDealPayout row created (immutable audit log).
    - XGPTransaction row created (ledger entry).
    - ContributionEvent row created (feeds PFT scoring).
    - Reputation + 1 and successful_coop_deals_count + 1.

    Note: This endpoint has no auth guard for MVP.  Add host-only or admin
    role check in a future step.
    """
    try:
        return complete_coop_deal(db=db, deal_id=body.deal_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get("/my")
def my_deals(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Return the authenticated player's co-op deal profile summary.

    Includes active hosted/joined deal counts, lifetime deal statistics
    (successful and failed), and current reputation score.
    """
    player = _get_player_or_404(current_user, db)
    return build_deals_summary(db=db, player=player)


@router.get("/history")
def deal_history(
    limit: int = Query(50, ge=1, le=200, description="Max records to return"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    """Return the authenticated player's co-op deal participation history.

    Each record shows the deal, the player's role, split percentage, payout
    amount (if completed), and deal status.  Ordered newest-first.
    """
    player = _get_player_or_404(current_user, db)

    participations = (
        db.query(CoopDealParticipant)
        .filter(CoopDealParticipant.player_id == player.id)
        .order_by(CoopDealParticipant.joined_at.desc())
        .limit(limit)
        .all()
    )

    result = []
    for part in participations:
        deal = db.query(CoopDeal).filter(CoopDeal.id == part.deal_id).first()
        if deal is None:
            continue

        payout = (
            db.query(CoopDealPayout)
            .filter(
                CoopDealPayout.deal_id == part.deal_id,
                CoopDealPayout.player_id == player.id,
            )
            .first()
        )

        result.append({
            "deal_id": deal.id,
            "template_id": deal.template_id,
            "display_name": deal.display_name,
            "role_id": part.role_id,
            "split_percent": part.split_percent,
            "is_host": part.is_host,
            "is_paid": part.is_paid,
            "payout_amount_xgp": float(payout.amount_xgp) if payout else None,
            "deal_status": deal.status,
            "created_day_number": deal.created_day_number,
            "expires_day_number": deal.expires_day_number,
            "completed_day_number": deal.completed_day_number,
            "joined_at": part.joined_at.isoformat() if part.joined_at else None,
        })

    return result


@router.post("/admin/expire")
def admin_expire_deals(
    body: ExpireDealsRequest,
    db: Session = Depends(get_db),
) -> dict:
    """Admin: expire all open deals whose expiry day has passed.

    Pass the current in-game day_number to expire all deals with
    expires_day_number <= day_number.

    Increments failed_coop_deals_count on the host of each expired deal.
    Safe to call repeatedly — already-expired deals are skipped.

    No auth guard for MVP — protect via network policy or admin role in future.
    """
    expired_count = expire_open_deals(db=db, current_day_number=body.day_number)
    return {
        "message": f"Expired {expired_count} open deal(s).",
        "expired_count": expired_count,
        "day_number": body.day_number,
    }
