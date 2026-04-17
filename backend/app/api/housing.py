"""Housing API — Step 7 (region cost layer) + Step 8 (property/debt system).

Route overview
--------------
Step 7 — Housing Region Cost Layer
  GET  /housing/regions           — All active living regions with daily costs
  POST /housing/assign            — Authenticated: choose/change housing region
  GET  /housing/me                — Authenticated: current region + daily cost info
  GET  /housing/payment-history   — Authenticated: daily housing payment audit log

Step 8 — Housing Property / Debt System (pre-existing)
  GET  /housing/options           — Static housing definitions with move-in costs
  POST /housing/move-in           — Authenticated: move into a housing arrangement
  GET  /housing/current           — Authenticated: current housing + debt summary
  POST /housing/apply-daily-cost  — Authenticated: apply daily housing cost for a day
  GET  /housing/debt              — Authenticated: all debt accounts for the player
  POST /housing/pay-debt          — Authenticated: make a manual debt payment
  GET  /housing/history           — Authenticated: housing action history (newest first)
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.db.database import get_db
from app.engine.housing_engine import (
    HousingEngine,
    get_or_seed_default_housing_regions,
    get_housing_region_by_id,
    calculate_daily_housing_cost,
    calculate_housing_stress_modifier,
    validate_housing_assignment,
)
from app.models.housing_payment import HousingPayment
from app.models.player import Player
from app.models.user import User
from app.services.housing_region_service import (
    HousingNotFoundError,
    HousingRegionError,
    HousingValidationError,
    assign_player_housing,
    compute_daily_housing_region_effects,
    get_player_housing_history,
    get_player_housing_logs,
    get_player_housing_snapshot,
    get_player_housing_summary,
    update_player_region,
)

router = APIRouter()
_engine = HousingEngine()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_player_or_404(user: User, db: Session) -> Player:
    player = db.query(Player).filter(Player.user_id == str(user.id)).first()
    if player is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Player profile not found.",
        )
    return player


def _get_player_by_id_or_404(player_id: str, db: Session) -> Player:
    try:
        pid = UUID(str(player_id))
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Player profile not found.",
        )
    player = db.query(Player).filter(Player.id == pid).first()
    if player is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Player profile not found.",
        )
    return player


def _raise_housing_service_http_error(exc: Exception) -> None:
    if isinstance(exc, HousingNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, HousingValidationError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if isinstance(exc, HousingRegionError):
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected housing service error.")


# ─────────────────────────────────────────────────────────────────────────────
# Step 7 — Pydantic schemas
# ─────────────────────────────────────────────────────────────────────────────


class HousingRegionResponse(BaseModel):
    """One row from the housing_regions table, as returned to the frontend."""
    region_id: str
    display_name: str
    daily_cost: float
    stress_modifier: int
    is_active: bool


class HousingAssignRequest(BaseModel):
    """Request body for POST /housing/assign."""
    player_id: str | None = Field(
        default=None,
        description="Target player UUID. If omitted, uses authenticated player.",
    )
    region: str | None = Field(default=None, description="'suburban' or 'downtown'")
    region_id: str | None = Field(default=None, description="Backward-compatible alias for region")
    housing_type: str = Field(default="starter_rent", description="MVP housing type")


class HousingMeResponse(BaseModel):
    """Current housing region info for the authenticated player."""
    housing_region_id: Optional[str]
    display_name: Optional[str]
    daily_cost: Optional[float]
    stress_modifier: Optional[int]
    message: str  # human-readable context


class HousingPaymentHistoryItem(BaseModel):
    """One HousingPayment record, newest-first."""
    id: str
    region_id: str
    day_number: int
    amount: float
    balance_before: float
    balance_after: float
    created_at: Optional[str]

    class Config:
        from_attributes = True


class HousingRegionUpdateRequest(BaseModel):
    region_key: str = Field(..., description="'suburban' or 'downtown'")
    housing_type: str | None = Field(default=None, description="Optional housing type override")
    commute_mode: str | None = Field(default=None, description="Optional commute mode override")


class PlayerHousingSnapshot(BaseModel):
    player_id: str
    region_key: str
    housing_type: str
    monthly_housing_cost_xgp: float
    monthly_utilities_cost_xgp: float
    monthly_transport_base_xgp: float
    commute_mode: str
    networking_modifier: float
    region_opportunity_modifier: float
    region_business_demand_modifier: float
    region_side_income_modifier: float
    latest_daily: dict | None = None
    debug_meta: dict = Field(default_factory=dict)


class HousingRegionDailyResponse(BaseModel):
    player_id: str
    as_of_date: str | None = None
    day: int | None = None
    region_key: str
    housing_cost_daily_xgp: float
    utilities_cost_daily_xgp: float
    commute_hours: float
    commute_fuel_cost_xgp: float
    region_stress_delta: float
    region_opportunity_modifier: float
    region_business_demand_modifier: float
    region_side_income_modifier: float
    networking_modifier: float
    opportunity_quality_signal: float
    debug_meta: dict | None = None
    already_processed: bool = False


class HousingRegionHistoryResponse(BaseModel):
    player_id: str
    entries: list[dict] = Field(default_factory=list)
    trailing_7d_avg_commute_hours: float = 0.0
    trailing_7d_avg_housing_cost_xgp: float = 0.0
    trailing_7d_avg_region_stress_delta: float = 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Step 7 — Endpoints
# ─────────────────────────────────────────────────────────────────────────────


@router.get(
    "/regions",
    response_model=list[HousingRegionResponse],
    summary="List all active housing regions",
)
def get_housing_regions(db: Session = Depends(get_db)):
    """
    Return all active living regions for MVP: suburban and downtown.

    This endpoint is public — no auth required, so the frontend can display
    region costs and stress modifiers to all visitors.

    Economic context:
      - Suburban (18 XGP/day, stress -1):  cheaper, calmer, fewer opportunities.
      - Downtown (35 XGP/day, stress +2):  premium cost, more pressure, more
        future networking and opportunity potential.
    """
    regions = get_or_seed_default_housing_regions(db)
    return [
        HousingRegionResponse(
            region_id=r.region_id,
            display_name=r.display_name,
            daily_cost=float(r.daily_cost),
            stress_modifier=int(r.stress_modifier),
            is_active=bool(r.is_active),
        )
        for r in regions
    ]


@router.post(
    "/assign",
    summary="Assign or change housing region state",
)
def assign_housing_region(
    body: HousingAssignRequest,
    db: Session = Depends(get_db),
) -> dict:
    """
    Assign or replace player housing state (MVP region pressure layer).

    Supports both payload formats:
      - New: {player_id, region, housing_type}
      - Legacy: {region_id} with authenticated player omitted in this route
    """
    region_value = (body.region or body.region_id or "").strip().lower()
    if not region_value:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="region is required.")
    if not body.player_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="player_id is required.")

    try:
        player = _get_player_by_id_or_404(body.player_id, db)
        valid, reason = validate_housing_assignment(region_value)
        if not valid:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=reason)
        region = get_housing_region_by_id(db, region_value)
        if region is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Region '{region_value}' not found or is not currently active.",
            )
        result = assign_player_housing(
            db=db,
            player_id=str(player.id),
            region=region_value,
            housing_type=body.housing_type,
        )
        return result
    except HTTPException:
        raise
    except Exception as exc:
        _raise_housing_service_http_error(exc)


@router.get("/player/{player_id}", summary="Get player housing state and summary")
def get_player_housing_state(player_id: str, db: Session = Depends(get_db)) -> dict:
    """Return active housing state plus latest housing log summary for a player."""
    try:
        summary = get_player_housing_summary(db, player_id)
        snapshot = get_player_housing_snapshot(db, player_id)
        return {
            **summary,
            "snapshot": snapshot,
        }
    except Exception as exc:
        _raise_housing_service_http_error(exc)


@router.get("/logs/{player_id}", summary="Get player housing daily logs")
def get_player_housing_daily_logs(
    player_id: str,
    limit: int = Query(default=20, ge=1, le=200),
    db: Session = Depends(get_db),
) -> dict:
    """Return most recent housing daily logs for the player, newest first."""
    try:
        return get_player_housing_logs(db=db, player_id=player_id, limit=limit)
    except Exception as exc:
        _raise_housing_service_http_error(exc)


@router.post(
    "/player/{player_id}/region",
    response_model=PlayerHousingSnapshot,
    summary="Set or change player housing region",
)
def set_player_region(
    player_id: str,
    body: HousingRegionUpdateRequest,
    db: Session = Depends(get_db),
) -> PlayerHousingSnapshot:
    try:
        update_player_region(
            db=db,
            player_id=player_id,
            region_key=body.region_key,
            housing_type=body.housing_type,
            commute_mode=body.commute_mode,
        )
        db.commit()
        payload = get_player_housing_snapshot(db=db, player_id=player_id)
        return PlayerHousingSnapshot(**payload)
    except Exception as exc:
        db.rollback()
        _raise_housing_service_http_error(exc)


@router.get(
    "/player/{player_id}/history",
    response_model=HousingRegionHistoryResponse,
    summary="Get recent housing-region daily history for a player",
)
def get_player_housing_region_history(
    player_id: str,
    limit: int = Query(default=30, ge=1, le=180),
    db: Session = Depends(get_db),
) -> HousingRegionHistoryResponse:
    try:
        payload = get_player_housing_history(db=db, player_id=player_id, limit=limit)
        return HousingRegionHistoryResponse(**payload)
    except Exception as exc:
        _raise_housing_service_http_error(exc)


@router.get(
    "/player/{player_id}/daily/latest",
    response_model=HousingRegionDailyResponse,
    summary="Get latest housing-region daily effect for a player",
)
def get_player_housing_region_daily_latest(
    player_id: str,
    db: Session = Depends(get_db),
) -> HousingRegionDailyResponse:
    try:
        player = _get_player_by_id_or_404(player_id, db)
        target_day = max(int(player.last_settled_day or 0) + 1, 1)
        payload = compute_daily_housing_region_effects(db=db, player_id=player.id, day=target_day)
        db.commit()
        payload["debug_meta"] = payload.get("housing_debug_json")
        payload.setdefault("player_id", str(player.id))
        return HousingRegionDailyResponse(**payload)
    except Exception as exc:
        db.rollback()
        _raise_housing_service_http_error(exc)


@router.get(
    "/me",
    response_model=HousingMeResponse,
    summary="Get authenticated player's current housing region",
)
def get_my_housing(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Return the authenticated player's current housing region info.

    If no region has been assigned yet, returns null fields and a prompt
    to assign a region via POST /housing/assign.
    """
    player = _get_player_or_404(current_user, db)

    region_id = getattr(player, "housing_region_id", None)
    if not region_id:
        return HousingMeResponse(
            housing_region_id=None,
            display_name=None,
            daily_cost=None,
            stress_modifier=None,
            message=(
                "No housing region assigned. "
                "Use POST /housing/assign to set your living region."
            ),
        )

    region = get_housing_region_by_id(db, region_id)
    if region is None:
        return HousingMeResponse(
            housing_region_id=region_id,
            display_name=None,
            daily_cost=None,
            stress_modifier=None,
            message=(
                f"Region '{region_id}' is no longer active. "
                "Use POST /housing/assign to choose a new region."
            ),
        )

    return HousingMeResponse(
        housing_region_id=region.region_id,
        display_name=region.display_name,
        daily_cost=calculate_daily_housing_cost(region),
        stress_modifier=calculate_housing_stress_modifier(region),
        message=(
            f"Currently living in {region.display_name}. "
            f"Daily cost: {calculate_daily_housing_cost(region):.2f} XGP/day. "
            f"Settlement stress modifier: {calculate_housing_stress_modifier(region):+d}."
        ),
    )


@router.get(
    "/payment-history",
    response_model=list[HousingPaymentHistoryItem],
    summary="Get authenticated player's housing payment history",
)
def get_housing_payment_history(
    limit: int = Query(default=20, ge=1, le=100),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Return the authenticated player's daily housing payment records, newest first.

    Each row represents one successful daily housing cost deduction.
    Days where housing could not be paid (insufficient funds) are NOT recorded
    here — they appear only in the settlement log's housing_stress_modifier field.

    Default: 20 records.  Maximum: 100.
    """
    player = _get_player_or_404(current_user, db)

    payments = (
        db.query(HousingPayment)
        .filter(HousingPayment.player_id == player.id)
        .order_by(HousingPayment.day_number.desc())
        .limit(limit)
        .all()
    )

    return [
        HousingPaymentHistoryItem(
            id=str(p.id),
            region_id=p.region_id,
            day_number=p.day_number,
            amount=float(p.amount),
            balance_before=float(p.balance_before),
            balance_after=float(p.balance_after),
            created_at=p.created_at.isoformat() if p.created_at else None,
        )
        for p in payments
    ]



# ── Request bodies ────────────────────────────────────────────────────────────

class MoveInRequest(BaseModel):
    housing_key: str


class ApplyDailyCostRequest(BaseModel):
    day: int = Field(..., ge=1, description="In-game day number to apply housing cost for")


class PayDebtRequest(BaseModel):
    debt_account_id: str
    amount: float = Field(..., gt=0, description="Amount to pay toward the debt principal")


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/options")
def get_housing_options() -> list[dict]:
    """Return all static housing definitions with computed move-in costs."""
    return _engine.list_housing_options()


@router.post("/move-in")
def move_in(
    body: MoveInRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Move player into a housing arrangement.

    For rent: deducts 3 days upfront.
    For own: deducts 10% down payment and creates a mortgage debt account.
    Updates player region and has_active_housing flag.
    """
    player = _get_player_or_404(current_user, db)
    try:
        return _engine.move_into_housing(player, body.housing_key, db)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get("/current")
def get_current_housing(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Return the player's current active housing and debt summary (if owned)."""
    player = _get_player_or_404(current_user, db)
    result = _engine.get_current_housing(player, db)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active housing arrangement found.",
        )
    return result


@router.post("/apply-daily-cost")
def apply_daily_housing_cost(
    body: ApplyDailyCostRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Apply daily housing cost for the specified in-game day.

    Idempotent: can only be applied once per day.
    Covers rent or mortgage + property tax + possible maintenance.
    Missed payments trigger credit/stability/stress penalties.
    """
    player = _get_player_or_404(current_user, db)
    try:
        return _engine.apply_daily_housing_cost(player, body.day, db)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get("/debt")
def get_debt(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    """Return all debt accounts for the player (mortgage, emergency_debt, etc.)."""
    player = _get_player_or_404(current_user, db)
    return _engine.get_debt_accounts(player, db)


@router.post("/pay-debt")
def pay_debt(
    body: PayDebtRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Make an extra manual payment on a debt account.

    Reduces principal balance. Cannot exceed the current principal.
    Incrementally improves delinquency status if applicable.
    """
    player = _get_player_or_404(current_user, db)
    try:
        return _engine.pay_debt(player, body.debt_account_id, body.amount, db)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get("/history")
def get_housing_history(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    """Return housing action history for the player, newest first (limit 100)."""
    player = _get_player_or_404(current_user, db)
    return _engine.get_housing_history(player, db)
