from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from uuid import UUID

from app.api.auth import get_current_user
from app.db.database import get_db
from app.engine.work_engine import WorkEngine
from app.models.job_action import JobAction
from app.models.job_definition import JOB_CATALOG, MAIN_JOBS, SIDE_JOBS, resolve_job_definition
from app.models.player import Player
from app.models.user import User
from app.services.job_key_service import normalize_main_job_key, supported_main_job_keys_text
from app.services.daily_settlement_service import get_next_player_day
from app.services.job_market_service import (
    JobMarketError,
    JobMarketNotFoundError,
    JobMarketValidationError,
    apply_employment_progression,
    compute_job_market_pressure,
    get_player_job_summary,
)
from app.services.player_onboarding_service import DAY_ONE_SURVIVAL_JOB_KEYS, is_day_one_survival_window

router = APIRouter()
_engine = WorkEngine()


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class WorkRequest(BaseModel):
    job_name: str = Field(..., description="Job name from the catalog (e.g. 'banker', 'rideshare')")
    hours_worked: int = Field(..., ge=1, le=12, description="Hours to work this shift (1-12)")


class UpdatedPlayerSnapshot(BaseModel):
    cash: float
    health: int
    stress: int
    fatigue: float
    total_hours_worked_today: int
    work_actions_today: int


class WorkResponse(BaseModel):
    message: str
    job: str
    job_type: str
    shift_number: int
    hours_worked: int
    productivity: float
    earned_cash: float
    stress_change: int
    health_change: int
    fatigue_change: float
    overtime_penalty_applied: bool
    hours_remaining: int
    updated_player: UpdatedPlayerSnapshot


class JobDefinitionOut(BaseModel):
    name: str
    category: str
    monthly_salary: float
    base_stress: int
    stability: float
    growth: float
    layoff_risk: float
    physical_load: float
    mental_load: float
    hourly_pay: float       # computed convenience field


class JobListResponse(BaseModel):
    main_jobs: list[JobDefinitionOut]
    side_jobs: list[JobDefinitionOut]


class JobActionOut(BaseModel):
    id: str
    job_name: str
    job_type: str
    shift_number: int
    day: int
    hours_worked: int
    base_hourly_pay: float
    productivity: float
    earned_cash: float
    stress_change: int
    health_change: int
    fatigue_change: float
    overtime_penalty_applied: bool
    hours_remaining_after: int
    created_at: str


# ── Helper ────────────────────────────────────────────────────────────────────

def _get_player_or_404(user: User, db: Session) -> Player:
    player = db.query(Player).filter(Player.user_id == str(user.id)).first()
    if player is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Player profile not found.")
    return player


def _get_player_by_id_or_404(player_id: str, db: Session) -> Player:
    try:
        pid = UUID(str(player_id))
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Player profile not found.")
    player = db.query(Player).filter(Player.id == pid).first()
    if player is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Player profile not found.")
    return player


def _raise_job_market_http_error(exc: Exception) -> None:
    if isinstance(exc, JobMarketNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, JobMarketValidationError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if isinstance(exc, JobMarketError):
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected job-market service error.")


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get(
    "/list",
    response_model=JobListResponse,
    summary="List all available jobs grouped by category",
)
def list_jobs() -> JobListResponse:
    """
    Returns all static job definitions split into main jobs and side jobs.
    No authentication required.
    """

    def _to_out(name: str) -> JobDefinitionOut:
        j = JOB_CATALOG[name]
        return JobDefinitionOut(
            name=j.name,
            category=j.category,
            monthly_salary=j.monthly_salary,
            base_stress=j.base_stress,
            stability=j.stability,
            growth=j.growth,
            layoff_risk=j.layoff_risk,
            physical_load=j.physical_load,
            mental_load=j.mental_load,
            hourly_pay=round(j.monthly_salary / 30 / 8, 4),
        )

    return JobListResponse(
        main_jobs=[_to_out(n) for n in sorted(MAIN_JOBS)],
        side_jobs=[_to_out(n) for n in sorted(SIDE_JOBS)],
    )


@router.post(
    "/work",
    response_model=WorkResponse,
    status_code=status.HTTP_200_OK,
    summary="Perform a work shift",
)
def work(
    body: WorkRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WorkResponse:
    """
    Processes a single work shift for the authenticated player.

    Rules enforced:
    - Max 2 work actions per in-game day (1 main + 1 side)
    - Main job: max 8 h/day; Side job: max 4 h/day; Total: max 12 h/day
    - Health must be above 15 to work
    - Fatigue must be below 90 for a second shift
    - Second shift applies productivity penalty and increased stress/fatigue
    """
    player = _get_player_or_404(current_user, db)

    try:
        result = _engine.process_work_action(
            db=db,
            player=player,
            job_name=body.job_name,
            hours_worked=body.hours_worked,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    return WorkResponse(
        message="Work completed.",
        job=result.job_name,
        job_type=result.job_type,
        shift_number=result.shift_number,
        hours_worked=result.hours_worked,
        productivity=result.productivity,
        earned_cash=result.earned_cash,
        stress_change=result.stress_change,
        health_change=result.health_change,
        fatigue_change=result.fatigue_change,
        overtime_penalty_applied=result.overtime_penalty_applied,
        hours_remaining=result.hours_remaining_after,
        updated_player=UpdatedPlayerSnapshot(
            cash=result.player_cash,
            health=result.player_health,
            stress=result.player_stress,
            fatigue=result.player_fatigue,
            total_hours_worked_today=result.player_total_hours_worked_today,
            work_actions_today=result.player_work_actions_today,
        ),
    )


@router.get(
    "/history",
    response_model=list[JobActionOut],
    summary="Get recent work history for the authenticated player",
)
def get_work_history(
    limit: int = Query(default=20, ge=1, le=100, description="Max records to return"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[JobActionOut]:
    """
    Returns the player's recent work actions, newest first.
    """
    player = _get_player_or_404(current_user, db)

    actions = (
        db.query(JobAction)
        .filter(JobAction.player_id == player.id)
        .order_by(JobAction.created_at.desc())
        .limit(limit)
        .all()
    )

    return [
        JobActionOut(
            id=str(a.id),
            job_name=a.job_name,
            job_type=a.job_type,
            shift_number=a.shift_number,
            day=a.day,
            hours_worked=a.hours_worked,
            base_hourly_pay=float(a.base_hourly_pay),
            productivity=a.productivity,
            earned_cash=float(a.earned_cash),
            stress_change=a.stress_change,
            health_change=a.health_change,
            fatigue_change=a.fatigue_change,
            overtime_penalty_applied=a.overtime_penalty_applied,
            hours_remaining_after=a.hours_remaining_after,
            created_at=a.created_at.isoformat(),
        )
        for a in actions
    ]


# ── POST /jobs/assign ─────────────────────────────────────────────────────────


class AssignJobRequest(BaseModel):
    """Request body for POST /jobs/assign.

    Example::

        { "job_id": "banker" }
    """

    job_id: str = Field(
        ...,
        description="Job identifier from GET /jobs/list (main jobs only).",
        examples=["banker"],
    )


class AssignJobResponse(BaseModel):
    message: str
    job_id: str
    display_name: str
    monthly_salary: float
    hourly_pay: float


class JobMarketResponse(BaseModel):
    player_id: str
    day: int
    current_job_code: str | None
    employment_status: str
    opportunity_score: float
    layoff_risk_pct: float
    promotion_chance_pct: float
    wage_adjustment_pct: float
    productivity_modifier: float
    region: str
    region_opportunity_modifier: float
    commute_modifier: float
    macro_day_used: int


class JobEvaluateResponse(BaseModel):
    player_id: str
    day: int
    employment_status: str
    employment_event: str
    layoff_risk_pct: float
    promotion_chance_pct: float
    wage_adjustment_pct: float
    monthly_pay_before: float
    monthly_pay_after: float
    monthly_pay_xgp_after_event: float
    skill_level: int
    opportunity_score: float
    productivity_modifier: float
    promotion_count: int
    last_raise_pct: float
    already_processed: bool


class JobPlayerSummaryResponse(BaseModel):
    player_id: str
    current_job_code: str | None = None
    current_job_summary: dict | None = None
    current_status: str
    current_monthly_pay_xgp: float
    skill_level: int
    promotion_count: int
    last_employment_event: str | None = None


@router.post(
    "/assign",
    response_model=AssignJobResponse,
    status_code=status.HTTP_200_OK,
    summary="Assign or change the authenticated player's main job",
)
def assign_job(
    body: AssignJobRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AssignJobResponse:
    """Set or change the authenticated player's main job.

    Rules
    -----
    - Only main-job roles are accepted (side jobs cannot be assigned as main).
    - The job_id must exist in the static JOB_CATALOG.
    - Changing jobs takes effect immediately (no cooldown in MVP).

    Example request body::

        { "job_id": "banker" }
    """
    # Validate job exists.
    canonical_job_id = normalize_main_job_key(body.job_id, allow_aliases=False)
    job_def = resolve_job_definition(canonical_job_id)
    if job_def is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Unknown job_id '{body.job_id}'. "
                f"Valid job IDs: {supported_main_job_keys_text()}."
            ),
        )

    # Reject side jobs — players assign those separately.
    if job_def.category != "main":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"'{body.job_id}' is a side job and cannot be assigned as a main job. "
                f"Main jobs available: {sorted(MAIN_JOBS)}."
            ),
        )

    player = _get_player_or_404(current_user, db)
    if is_day_one_survival_window(player) and canonical_job_id not in DAY_ONE_SURVIVAL_JOB_KEYS:
        allowed_labels = ", ".join(sorted(job_key.replace("_", " ") for job_key in DAY_ONE_SURVIVAL_JOB_KEYS))
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Day 1 survival mode only allows starter jobs. Choose one of: {allowed_labels}.",
        )
    player.main_job = canonical_job_id
    db.commit()
    db.refresh(player)

    hourly = round(job_def.monthly_salary / 30 / 8, 4)
    return AssignJobResponse(
        message=f"Main job assigned to '{canonical_job_id}'.",
        job_id=str(canonical_job_id),
        display_name=job_def.name.replace("_", " ").title(),
        monthly_salary=job_def.monthly_salary,
        hourly_pay=hourly,
    )


@router.get(
    "/market/{player_id}",
    response_model=JobMarketResponse,
    summary="Compute current job-market pressure metrics for a player",
)
def get_job_market_snapshot(player_id: str, db: Session = Depends(get_db)) -> JobMarketResponse:
    """Read-only market pressure view (no mutation)."""
    try:
        _get_player_by_id_or_404(player_id, db)
        day = get_next_player_day(db, player_id)
        payload = compute_job_market_pressure(db=db, player_id=player_id, day=day)
        return JobMarketResponse(**payload)
    except HTTPException:
        raise
    except Exception as exc:
        _raise_job_market_http_error(exc)


@router.post(
    "/evaluate/{player_id}",
    response_model=JobEvaluateResponse,
    summary="Evaluate today's employment event for a player",
)
def evaluate_job_event(player_id: str, db: Session = Depends(get_db)) -> JobEvaluateResponse:
    """Mutating debug endpoint for layoff/promotion/wage progression."""
    try:
        _get_player_by_id_or_404(player_id, db)
        day = get_next_player_day(db, player_id)
        payload = apply_employment_progression(
            db=db,
            player_id=player_id,
            day=day,
            commit=True,
        )
        return JobEvaluateResponse(**payload)
    except HTTPException:
        raise
    except Exception as exc:
        _raise_job_market_http_error(exc)


@router.get(
    "/player/{player_id}",
    response_model=JobPlayerSummaryResponse,
    summary="Get latest employment summary for a player",
)
def get_job_player_summary(player_id: str, db: Session = Depends(get_db)) -> JobPlayerSummaryResponse:
    """Return latest employment snapshot with current status/pay context."""
    try:
        _get_player_by_id_or_404(player_id, db)
        payload = get_player_job_summary(db=db, player_id=player_id)
        return JobPlayerSummaryResponse(**payload)
    except HTTPException:
        raise
    except Exception as exc:
        _raise_job_market_http_error(exc)
