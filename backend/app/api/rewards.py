"""Rewards API — Step 5.5 + Step 9.

All routes are authenticated. No on-chain calls are made here.

Route overview
--------------
GET  /rewards/summary             — Player's current reward state
GET  /rewards/history             — Recent reward_ledger rows for the player
GET  /rewards/window/current      — Current/latest claim window settings
POST /rewards/process-month       — Finalize monthly reward for the player
POST /rewards/link-wallet         — Save a wallet address for future claims
GET  /rewards/suspicious-check    — Run suspicious-pattern scan (debug)

Step 9 — Monthly Reward Pool and Token Claim Accounting:
GET  /rewards/score               — Player's current granular reward score
GET  /rewards/monthly             — Monthly score + pool info + estimated tokens
GET  /rewards/allowance           — Claimable token allowances
POST /rewards/claim               — Mark monthly token allowance as claimed
GET  /rewards/claim-history       — Player token claim history
POST /rewards/pool/create         — Admin: create/get reward pool for a month
POST /rewards/pool/close          — Admin: close pool and calculate allowances
"""

import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.db.database import get_db
from app.engine.reward_engine import RewardEngine
from app.models.claim_window import ClaimWindow
from app.models.game_state import GameState
from app.models.player import Player
from app.models.reward_ledger import RewardLedger
from app.models.user import User
from app.models.wallet_link import WalletLink

router = APIRouter()
_engine = RewardEngine()

# ── Shared helpers ─────────────────────────────────────────────────────────────

_EVM_ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")
_SOLANA_ADDRESS_RE = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")
_SUPPORTED_CHAINS = {"base", "ethereum", "polygon", "arbitrum", "optimism", "solana"}


def _get_player_or_404(user: User, db: Session) -> Player:
    player = db.query(Player).filter(Player.user_id == user.id).first()
    if player is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Player profile not found.")
    return player


def _validate_wallet_address(wallet_address: str, chain_name: str) -> None:
    """Basic format validation — no signing verification in Step 5.5."""
    chain = chain_name.lower()
    if chain not in _SUPPORTED_CHAINS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unsupported chain '{chain_name}'. Supported: {sorted(_SUPPORTED_CHAINS)}.",
        )
    if chain == "solana":
        if not _SOLANA_ADDRESS_RE.match(wallet_address):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Invalid Solana wallet address format.",
            )
    else:
        if not _EVM_ADDRESS_RE.match(wallet_address):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Invalid EVM wallet address. Must be 0x followed by 40 hex characters.",
            )


# ── Request / response bodies ─────────────────────────────────────────────────

class ProcessMonthRequest(BaseModel):
    month_key: str  # "YYYY-MM"


class LinkWalletRequest(BaseModel):
    wallet_address: str
    chain_name: str = "base"


# ── GET /rewards/summary ───────────────────────────────────────────────────────

@router.get("/summary")
def get_reward_summary(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Return the authenticated player's current off-chain reward state."""
    player = _get_player_or_404(current_user, db)
    return _engine.get_player_reward_summary(player.id, db)


# ── GET /rewards/history ───────────────────────────────────────────────────────

@router.get("/history")
def get_reward_history(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    """Return recent reward ledger rows for the authenticated player, newest first."""
    player = _get_player_or_404(current_user, db)
    rows = (
        db.query(RewardLedger)
        .filter(RewardLedger.player_id == player.id)
        .order_by(RewardLedger.month_key.desc())
        .limit(24)
        .all()
    )
    return [
        {
            "month_key": r.month_key,
            "days_active": r.days_active,
            "total_work_actions": r.total_work_actions,
            "total_income_earned": float(r.total_income_earned),
            "consistency_score": r.consistency_score,
            "survival_score": r.survival_score,
            "productivity_score": r.productivity_score,
            "anti_exploit_score": r.anti_exploit_score,
            "raw_reward_points": r.raw_reward_points,
            "approved_reward_points": r.approved_reward_points,
            "token_conversion_rate": r.token_conversion_rate,
            "estimated_token_amount": r.estimated_token_amount,
            "monthly_cap_applied": r.monthly_cap_applied,
            "eligibility_status": r.eligibility_status,
            "notes": r.notes,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


# ── GET /rewards/window/current ────────────────────────────────────────────────

@router.get("/window/current")
def get_current_claim_window(db: Session = Depends(get_db)) -> dict:
    """Return the latest claim window settings."""
    window = (
        db.query(ClaimWindow)
        .order_by(ClaimWindow.month_key.desc())
        .first()
    )
    if window is None:
        return {
            "message": "No claim window exists yet.",
            "status": "none",
            "min_claim_threshold": 25.0,
            "max_claim_per_player": 200.0,
        }
    return {
        "month_key": window.month_key,
        "status": window.status,
        "total_pool": window.total_pool,
        "total_approved": window.total_approved,
        "total_claimed": window.total_claimed,
        "min_claim_threshold": window.min_claim_threshold,
        "max_claim_per_player": window.max_claim_per_player,
        "opens_at": window.opens_at.isoformat() if window.opens_at else None,
        "closes_at": window.closes_at.isoformat() if window.closes_at else None,
        "created_at": window.created_at.isoformat() if window.created_at else None,
    }


# ── POST /rewards/process-month ────────────────────────────────────────────────

@router.post("/process-month")
def process_month(
    body: ProcessMonthRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Calculate and finalize the authenticated player's monthly reward.

    Idempotent: re-running for the same month updates the ledger in place
    without double-crediting the claim balance delta.
    """
    player = _get_player_or_404(current_user, db)
    try:
        result = _engine.finalize_player_monthly_reward(player.id, body.month_key, db)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return result


# ── POST /rewards/link-wallet ──────────────────────────────────────────────────

@router.post("/link-wallet")
def link_wallet(
    body: LinkWalletRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Save a wallet address for future on-chain claim use.

    Only one active wallet per chain per player is allowed. Re-linking the
    same chain updates the existing record with the new address.
    No cryptographic signature verification is performed in Step 5.5.
    """
    player = _get_player_or_404(current_user, db)
    _validate_wallet_address(body.wallet_address, body.chain_name)

    chain = body.chain_name.lower()
    existing = (
        db.query(WalletLink)
        .filter(WalletLink.player_id == player.id, WalletLink.chain_name == chain)
        .first()
    )
    if existing is not None:
        existing.wallet_address = body.wallet_address
        existing.is_verified = False  # re-verification needed after address change
        link = existing
    else:
        link = WalletLink(
            player_id=player.id,
            wallet_address=body.wallet_address,
            chain_name=chain,
            is_verified=False,
        )
        db.add(link)

    player.wallet_linked = True
    db.commit()
    db.refresh(link)

    return {
        "message": "Wallet address saved.",
        "wallet_address": link.wallet_address,
        "chain_name": link.chain_name,
        "is_verified": link.is_verified,
        "linked_at": link.linked_at.isoformat() if link.linked_at else None,
    }


# ── GET /rewards/suspicious-check ─────────────────────────────────────────────

@router.get("/suspicious-check")
def suspicious_check(
    month_key: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Debug endpoint: run suspicious-pattern scan for the authenticated player."""
    player = _get_player_or_404(current_user, db)
    try:
        flags = _engine.flag_suspicious_reward_pattern(player.id, month_key, db)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return {
        "month_key": month_key,
        "flagged_patterns": flags,
        "suspicious": len(flags) > 0,
    }


# ════════════════════════════════════════════════════════════════════════════════
# Step 9: Monthly Reward Pool and Token Claim Accounting
# ════════════════════════════════════════════════════════════════════════════════

def _current_day_and_month(db: Session) -> tuple[int, int]:
    """Return (current_day, month_index) from the live game state."""
    state = db.query(GameState).order_by(GameState.id.asc()).first()
    day = int(state.current_day) if state else 1
    month = max(1, (day - 1) // 30 + 1)
    return day, month


# ── Request bodies (Step 9) ───────────────────────────────────────────────────

class ClaimRequest(BaseModel):
    month_index: int


class PoolRequest(BaseModel):
    month_index: int


# ── GET /rewards/score ────────────────────────────────────────────────────────

@router.get("/score")
def get_reward_score(
    month_index: Optional[int] = Query(
        None, ge=1, description="Game month index (default: current month)"
    ),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Return the player's granular reward score breakdown for a game month.

    Includes work_points, business_points, investment_points,
    marketplace_points, stability_points, and total_points.
    """
    player = _get_player_or_404(current_user, db)
    _, current_month = _current_day_and_month(db)
    target_month = month_index if month_index is not None else current_month
    return _engine.get_player_score(player, target_month, db)


# ── GET /rewards/monthly ──────────────────────────────────────────────────────

@router.get("/monthly")
def get_monthly_summary(
    month_index: Optional[int] = Query(
        None, ge=1, description="Game month index (default: current month)"
    ),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Return player score + pool info + estimated token allocation for a month.

    Includes current pool status, total pool size, current points_total
    (if pool is closed), and estimated player token share.

    Note: estimated_tokens is an approximation until the pool is closed.
    Final allocation is determined by close_reward_pool().
    """
    player = _get_player_or_404(current_user, db)
    _, current_month = _current_day_and_month(db)
    target_month = month_index if month_index is not None else current_month
    return _engine.get_monthly_summary(player, target_month, db)


# ── GET /rewards/allowance ────────────────────────────────────────────────────

@router.get("/allowance")
def get_allowance(
    month_index: Optional[int] = Query(
        None, ge=1, description="Filter to a specific game month (default: all months)"
    ),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    """Return the player's token claim allowances.

    If month_index is provided, returns only that month's allowance.
    Otherwise returns all months newest-first.

    allowance_status values:
    - pending    — pool not yet closed
    - claimable  — pool closed; player can claim
    - claimed    — already claimed
    - expired    — claim window passed
    """
    player = _get_player_or_404(current_user, db)
    return _engine.get_player_allowances(player, db, month_index=month_index)


# ── POST /rewards/claim ───────────────────────────────────────────────────────

@router.post("/claim")
def claim_tokens(
    body: ClaimRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Mark the player's monthly token allowance as claimed.

    Requirements:
    - Allowance for month_index must exist and be in 'claimable' status.
    - The pool must have been closed first (via /rewards/pool/close).
    - Cannot claim the same month twice.

    Note: Actual blockchain minting happens in a future step.
    This records the off-chain claim intent.
    """
    player = _get_player_or_404(current_user, db)
    try:
        return _engine.claim_tokens(player, body.month_index, db)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


# ── GET /rewards/claim-history ────────────────────────────────────────────────

@router.get("/claim-history")
def get_claim_history(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    """Return the player's full token claim history newest-first."""
    player = _get_player_or_404(current_user, db)
    return _engine.get_claim_history(player, db)


# ── POST /rewards/pool/create — Admin/system: create reward pool ───────────────

@router.post("/pool/create")
def create_pool(
    body: PoolRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Create (or return existing) reward pool for a given game month.

    Idempotent: if pool already exists for month_index, returns it unchanged.
    Emits 100,000 tokens per month (MVP emission schedule).
    """
    _get_player_or_404(current_user, db)  # require authentication
    current_day, _ = _current_day_and_month(db)
    pool = _engine.get_or_create_reward_pool(body.month_index, current_day, db)
    return {
        "month_index": pool.month_index,
        "total_tokens_allocated": pool.total_tokens_allocated,
        "tokens_remaining": pool.tokens_remaining,
        "status": pool.status,
        "created_day": pool.created_day,
        "closed_day": pool.closed_day,
    }


# ── POST /rewards/pool/close — Admin/system: close pool and distribute ─────────

@router.post("/pool/close")
def close_pool(
    body: PoolRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Close the reward pool for a game month and calculate player allowances.

    Proportional distribution:
        player_tokens = pool_tokens × (player_points / total_points)

    Creates a TokenClaimAllowance row for every player with > 0 points.
    Players can then call POST /rewards/claim to mark their tokens.

    Raises 400 if pool does not exist or is already closed.
    """
    _get_player_or_404(current_user, db)  # require authentication
    current_day, _ = _current_day_and_month(db)
    try:
        return _engine.close_reward_pool(body.month_index, current_day, db)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


# ═══════════════════════════════════════════════════════════════════════════════
# Step 1 — Monetary constitution: epoch management and PFT simulation
#
# These are internal/admin-style endpoints.  In production they should be
# protected by an admin role or a separate internal API key middleware.
# For now they are open but clearly scoped under /rewards/.
#
# Economic design reminder:
#   XGP  — off-chain gameplay currency (wages, goods, services)
#   PFT  — on-chain ERC-20 reward token (Penny Float Token)
#   Allocation: player_pft = (score / total_qualified_score) × monthly_pool
#   Direct XGP→PFT conversion is intentionally DISABLED.
# ═══════════════════════════════════════════════════════════════════════════════

from datetime import date, datetime

from app.core.contribution_rules import CONTRIBUTION_WEIGHTS
from app.core.reward_policy import REWARD_POLICY
from app.core.token_config import TOKEN_CONFIG
from app.engine.reward_engine import (
    allocate_monthly_pft,
    calculate_player_contribution_score,
    is_player_reward_eligible,
    simulate_epoch_allocation,
)
from app.models.contribution_snapshot import ContributionSnapshot
from app.models.reward_epoch import RewardEpoch

# ── Pydantic schemas ───────────────────────────────────────────────────────────


class EpochCreateRequest(BaseModel):
    """Payload for POST /rewards/epoch/create."""

    season_number: int
    start_date: datetime
    end_date: datetime
    # PFT units available for this epoch.  Must not be negative and should
    # not exceed REWARD_POLICY["monthly_reward_pool"] under normal operation.
    reward_pool: float
    label: Optional[str] = None

    class Config:
        json_schema_extra = {
            "example": {
                "season_number": 1,
                "start_date": "2026-03-01T00:00:00Z",
                "end_date": "2026-03-31T23:59:59Z",
                "reward_pool": 50000000,
                "label": "2026-03",
            }
        }


class EpochResponse(BaseModel):
    """Epoch detail returned by epoch endpoints."""

    id: str
    season_number: int
    label: Optional[str]
    start_date: datetime
    end_date: datetime
    reward_pool: float
    is_finalized: bool
    created_at: datetime


class SimulationPlayerInput(BaseModel):
    """Input for one player's activity in a dry-run simulation.

    Example payload for POST /rewards/simulate:

        {
          "players": [
            {
              "player_id": 1,
              "account_age_days": 45,
              "reputation": 30,
              "job_work_xgp": 500,
              "business_profit_xgp": 200,
              "market_trade_volume_xgp": 100,
              "co_op_deals_completed": 2,
              "penalty_points": 0
            },
            {
              "player_id": 2,
              "account_age_days": 10,
              "reputation": 25,
              "job_work_xgp": 800,
              "business_profit_xgp": 0,
              "market_trade_volume_xgp": 50,
              "co_op_deals_completed": 1,
              "penalty_points": 0
            }
          ]
        }

    Player 1 qualifies (age 45 >= 30, rep 30 >= 20, score will exceed 100).
    Player 2 fails because account_age_days (10) < min_account_age_days (30).
    """

    player_id: int
    account_age_days: int = 0
    reputation: int = 0
    job_work_xgp: float = 0.0
    business_profit_xgp: float = 0.0
    market_trade_volume_xgp: float = 0.0
    co_op_deals_completed: int = 0
    penalty_points: int = 0


class SimulationRequest(BaseModel):
    """Request body for POST /rewards/simulate."""

    players: list[SimulationPlayerInput]
    # Optional: override the monthly pool for what-if analysis.
    monthly_reward_pool: Optional[float] = None

    class Config:
        json_schema_extra = {
            "example": {
                "players": [
                    {
                        "player_id": 1,
                        "account_age_days": 45,
                        "reputation": 30,
                        "job_work_xgp": 500,
                        "business_profit_xgp": 200,
                        "market_trade_volume_xgp": 100,
                        "co_op_deals_completed": 2,
                        "penalty_points": 0,
                    },
                    {
                        "player_id": 2,
                        "account_age_days": 10,
                        "reputation": 25,
                        "job_work_xgp": 800,
                        "business_profit_xgp": 0,
                        "market_trade_volume_xgp": 50,
                        "co_op_deals_completed": 1,
                        "penalty_points": 0,
                    },
                ]
            }
        }


class SimulationAllocationItem(BaseModel):
    player_id: int
    qualified: bool
    contribution_score: float
    pft_allocated: float


class SimulationResponse(BaseModel):
    total_players: int
    qualified_players: int
    total_contribution_score: float
    total_qualified_contribution_score: float
    monthly_reward_pool: float
    allocations: list[SimulationAllocationItem]
    policy_used: dict
    token_config: dict


# ── Helper ─────────────────────────────────────────────────────────────────────

def _epoch_to_dict(epoch: RewardEpoch) -> dict:
    return {
        "id": str(epoch.id),
        "season_number": epoch.season_number,
        "label": epoch.label,
        "start_date": epoch.start_date.isoformat(),
        "end_date": epoch.end_date.isoformat(),
        "reward_pool": float(epoch.reward_pool),
        "is_finalized": epoch.is_finalized,
        "created_at": epoch.created_at.isoformat() if epoch.created_at else None,
    }


# ── POST /rewards/epoch/create ── (internal/admin) ─────────────────────────────

@router.post("/epoch/create", tags=["Rewards"])
def create_epoch(body: EpochCreateRequest, db: Session = Depends(get_db)) -> dict:
    """Create a new monthly PFT reward epoch.

    Validations
    -----------
    * reward_pool must be >= 0.
    * end_date must be after start_date.
    * season_number must be >= 1.

    Returns the created epoch.  Does not check for duplicate periods — the
    caller is responsible for creating at most one epoch per calendar month.

    NOTE: This is an internal admin endpoint.  Add role-based auth middleware
    before exposing it publicly.
    """
    # Validations
    if body.reward_pool < 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="reward_pool cannot be negative.",
        )
    if body.end_date <= body.start_date:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="end_date must be after start_date.",
        )
    if body.season_number < 1:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="season_number must be >= 1.",
        )

    epoch = RewardEpoch(
        season_number=body.season_number,
        label=body.label,
        start_date=body.start_date,
        end_date=body.end_date,
        reward_pool=body.reward_pool,
        is_finalized=False,
    )
    db.add(epoch)
    db.commit()
    db.refresh(epoch)
    return _epoch_to_dict(epoch)


# ── POST /rewards/epoch/{epoch_id}/finalize ── (internal/admin) ────────────────

@router.post("/epoch/{epoch_id}/finalize", tags=["Rewards"])
def finalize_epoch(epoch_id: str, db: Session = Depends(get_db)) -> dict:
    """Mark an epoch as finalised.

    Once finalised, no further contribution snapshots should be written for
    this epoch.  The allocation engine can then run its final PFT distribution.

    Returns 400 if the epoch is already finalised.
    Returns 404 if the epoch does not exist.

    NOTE: Internal admin endpoint — add auth before exposing publicly.
    """
    epoch = db.query(RewardEpoch).filter(RewardEpoch.id == epoch_id).first()
    if epoch is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Epoch '{epoch_id}' not found.",
        )
    if epoch.is_finalized:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Epoch '{epoch_id}' is already finalised.",
        )
    epoch.is_finalized = True
    db.commit()
    db.refresh(epoch)
    return _epoch_to_dict(epoch)


# ── GET /rewards/epoch/{epoch_id} ─────────────────────────────────────────────

@router.get("/epoch/{epoch_id}", tags=["Rewards"])
def get_epoch(epoch_id: str, db: Session = Depends(get_db)) -> dict:
    """Return details for a single reward epoch."""
    epoch = db.query(RewardEpoch).filter(RewardEpoch.id == epoch_id).first()
    if epoch is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Epoch '{epoch_id}' not found.",
        )
    return _epoch_to_dict(epoch)


# ── GET /rewards/player/{player_id} ──────────────────────────────────────────

@router.get("/player/{player_id}", tags=["Rewards"])
def get_player_snapshots(player_id: str, db: Session = Depends(get_db)) -> list[dict]:
    """Return all contribution snapshots for a player, newest first.

    Returns an empty list if the player has no snapshots yet.

    NOTE: Internal endpoint.  In production, restrict to the authenticated
    player or admin roles to avoid data leakage.
    """
    snapshots = (
        db.query(ContributionSnapshot)
        .filter(ContributionSnapshot.player_id == player_id)
        .order_by(ContributionSnapshot.created_at.desc())
        .all()
    )
    return [
        {
            "id": str(s.id),
            "player_id": str(s.player_id),
            "epoch_id": str(s.epoch_id),
            "xgp_earned": s.xgp_earned,
            "contribution_score": s.contribution_score,
            "reputation_at_snapshot": s.reputation_at_snapshot,
            "qualified": s.qualified,
            "pft_allocated": s.pft_allocated,
            "claimed": s.claimed,
            "claimed_at": s.claimed_at.isoformat() if s.claimed_at else None,
            "created_at": s.created_at.isoformat() if s.created_at else None,
        }
        for s in snapshots
    ]


# ── POST /rewards/simulate ────────────────────────────────────────────────────

@router.post("/simulate", tags=["Rewards"])
def simulate_rewards(body: SimulationRequest) -> SimulationResponse:
    """Dry-run PFT allocation for a set of player activity inputs.

    Does NOT write anything to the database.  No blockchain actions are
    triggered.  Use this to preview how the reward pool would be distributed
    given a particular snapshot of player activity.

    Eligibility is evaluated against the canonical REWARD_POLICY.
    Contribution scores are computed using CONTRIBUTION_WEIGHTS.
    The monthly_reward_pool from the request body overrides the policy default
    when provided (useful for what-if scenarios).

    Example request body
    --------------------
    See SimulationPlayerInput docstring for a full example payload.

    Player 1 (account_age_days=45, rep=30, decent activity) → qualifies.
    Player 2 (account_age_days=10)                           → fails age gate.
    """
    policy = dict(REWARD_POLICY)  # copy so we don't mutate the global
    if body.monthly_reward_pool is not None:
        if body.monthly_reward_pool < 0:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="monthly_reward_pool cannot be negative.",
            )
        policy["monthly_reward_pool"] = body.monthly_reward_pool

    # Build lightweight snapshot objects from the request payload.
    class _Snap:
        """Minimal in-memory snapshot used only inside this endpoint."""
        __slots__ = (
            "player_id", "contribution_score", "qualified", "pft_allocated",
            "account_age_days", "reputation",
        )

    class _MockPlayer:
        """Minimal player stand-in that satisfies is_player_reward_eligible()."""
        __slots__ = ("reputation", "created_at")

    snaps: list[_Snap] = []
    for item in body.players:
        # Compute contribution score
        score = calculate_player_contribution_score(
            job_work_xgp=item.job_work_xgp,
            business_profit_xgp=item.business_profit_xgp,
            market_trade_volume_xgp=item.market_trade_volume_xgp,
            co_op_deals_completed=item.co_op_deals_completed,
            reputation=item.reputation,
            penalty_points=item.penalty_points,
        )

        snap = _Snap()
        snap.player_id = item.player_id
        snap.contribution_score = score
        snap.pft_allocated = 0.0

        # Eligibility: use a simulated player object driven by input fields.
        mock_player = _MockPlayer()
        mock_player.reputation = item.reputation
        # Synthesise created_at from account_age_days so the age gate works.
        from datetime import timedelta, timezone as _tz
        mock_player.created_at = datetime.now(_tz.utc) - timedelta(days=item.account_age_days)

        snap.qualified = is_player_reward_eligible(mock_player, snap, policy)
        snaps.append(snap)

    result = simulate_epoch_allocation(snaps, policy)

    return SimulationResponse(
        total_players=result["total_players"],
        qualified_players=result["qualified_players"],
        total_contribution_score=result["total_contribution_score"],
        total_qualified_contribution_score=result["total_qualified_contribution_score"],
        monthly_reward_pool=result["monthly_reward_pool"],
        allocations=[
            SimulationAllocationItem(**a) for a in result["allocations"]
        ],
        policy_used=policy,
        token_config=TOKEN_CONFIG,
    )
