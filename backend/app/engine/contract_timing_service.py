"""Step 41: Contracts, Recurring Obligations, and Calendar Pressure Layer.

This service computes and persists the timing-dimension of a player's financial life.
TIMING MATTERS SEPARATELY FROM TOTAL WEALTH.

Two players with identical net worth but different payment/income due-date distributions
will have different timing pressure, different bridge-borrow rationality scores, and
different forward planning risk windows.

Key insight outputs:
  - timing_pressure_label: low / manageable / elevated / severe
  - clustering_label:       spread / mild_cluster / clustered / heavily_clustered
  - bridge_need_label:      none / pre_payday_squeeze / moderate / urgent
  - obligation_collision_label: none / overlap / collision / compound

Sources (read-only):
  - PlayerHousingState   → rent + utilities cadence
  - PlayerEmploymentState → salary cadence
  - PlayerLoanAccount     → debt service schedule
  - PlayerBusiness        → overhead cadence
  - Player                → cash on hand
  - PlayerBorrowingState  → bridge borrow context

Write tables:
  - player_contract_schedules   (rolling per-player state, upsert by player)
  - player_contract_events      (bounded obligation/income event log, upsert by key+day)
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.database import Base  # noqa: F401 – ensure mapper is ready
from app.models.player import Player
from app.models.player_borrowing_state import PlayerBorrowingState
from app.models.player_business import PlayerBusiness
from app.models.player_contract_event import PlayerContractEvent
from app.models.player_contract_schedule import PlayerContractSchedule
from app.models.player_delinquency_state import PlayerDelinquencyState
from app.models.player_employment_state import PlayerEmploymentState
from app.models.player_housing_state import PlayerHousingState
from app.models.player_loan_account import PlayerLoanAccount

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

GAME_EPOCH = date(2026, 1, 1)
Q4 = Decimal("0.0001")
Q2 = Decimal("0.01")

# How many days forward to generate contract events
EVENT_FORWARD_WINDOW = 60    # generate obligations 60 days ahead
EVENT_BACKWARD_PRUNE = 14   # prune events older than 14 days (keep late ones)

# Default obligation cycles (days)
RENT_CYCLE = 30
UTILITIES_CYCLE = 30
INSURANCE_CYCLE = 30
PHONE_CYCLE = 30
OVERHEAD_CYCLE = 30
SALARY_CYCLE_DEFAULT = 30
SALARY_CYCLE_BIWEEKLY = 14
BUSINESS_PAYOUT_CYCLE = 30

# Fixed placeholder amounts for player accounts that have active housing/business
# but no stored monthly cost (safety fallback only)
PLACEHOLDER_RENT_XGP = Decimal("400")
PLACEHOLDER_UTILITIES_XGP = Decimal("80")
PLACEHOLDER_OVERHEAD_XGP = Decimal("150")
PLACEHOLDER_INSURANCE_XGP = Decimal("60")
PLACEHOLDER_PHONE_XGP = Decimal("30")

# Contract density score thresholds for clustering labels
# density_score = (obligations due in same 3-day window) / total_obligations_in_window
CLUSTER_MILD = Decimal("30")
CLUSTER_MODERATE = Decimal("55")
CLUSTER_HEAVY = Decimal("75")

# Timing pressure label thresholds (density_score 0-100)
PRESSURE_LOW_THRESHOLD = Decimal("30")
PRESSURE_MANAGEABLE_THRESHOLD = Decimal("50")
PRESSURE_ELEVATED_THRESHOLD = Decimal("70")

# Cash-gap bridge thresholds
BRIDGE_MINOR_THRESHOLD = Decimal("100")
BRIDGE_MODERATE_THRESHOLD = Decimal("400")
BRIDGE_URGENT_THRESHOLD = Decimal("900")

# Short-window (days) for due-today / due-soon markers
DUE_TODAY_WINDOW = 1
DUE_3D_WINDOW = 3
DUE_7D_WINDOW = 7

# Max "major" obligation for upcoming window (rent/loan = always major)
MAJOR_OBLIGATION_FAMILIES = {"personal", "debt"}

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class ContractTimingError(Exception):
    """Base Step 41 error."""


class ContractTimingNotFoundError(ContractTimingError):
    """Raised when player or required state rows are missing."""


class ContractTimingValidationError(ContractTimingError):
    """Raised for invalid inputs."""


# ---------------------------------------------------------------------------
# Precision helpers
# ---------------------------------------------------------------------------


def _d(value: object) -> Decimal:
    return Decimal(str(value or 0))


def _q4(value: Decimal) -> Decimal:
    return value.quantize(Q4, rounding=ROUND_HALF_UP)


def _q2(value: Decimal) -> Decimal:
    return value.quantize(Q2, rounding=ROUND_HALF_UP)


def _clamp(value: Decimal, lo: Decimal = Decimal("0"), hi: Decimal = Decimal("100")) -> Decimal:
    return max(lo, min(hi, value))


def _dump_json(payload: dict | list) -> str:
    return json.dumps(payload, sort_keys=True, default=str)


# ---------------------------------------------------------------------------
# Day / date helpers
# ---------------------------------------------------------------------------


def _day_to_date(day: int) -> date:
    if int(day) <= 0:
        raise ContractTimingValidationError("day must be greater than 0.")
    return GAME_EPOCH + timedelta(days=int(day) - 1)


def _date_to_day(as_of_date: date) -> int:
    day = int((as_of_date - GAME_EPOCH).days) + 1
    if day <= 0:
        raise ContractTimingValidationError("as_of_date must be on or after game epoch.")
    return day


def _resolve_day(day_number: int | None) -> tuple[int, date]:
    if day_number is not None:
        d = int(day_number)
        return d, _day_to_date(d)
    today = date.today()
    return _date_to_day(today), today


# ---------------------------------------------------------------------------
# DB fetch helpers
# ---------------------------------------------------------------------------


def _get_player(db: Session, player_id: str | UUID) -> Player:
    try:
        pid = player_id if isinstance(player_id, UUID) else UUID(str(player_id))
    except ValueError as exc:
        raise ContractTimingValidationError(f"Invalid player_id: {player_id}") from exc
    player = db.query(Player).filter(Player.id == pid).first()
    if player is None:
        raise ContractTimingNotFoundError(f"Player {player_id} not found.")
    return player


def _get_housing_state(db: Session, player_id: UUID) -> PlayerHousingState | None:
    return (
        db.query(PlayerHousingState)
        .filter(PlayerHousingState.player_id == player_id, PlayerHousingState.active_flag == True)  # noqa: E712
        .first()
    )


def _get_employment_state(db: Session, player_id: UUID) -> PlayerEmploymentState | None:
    return (
        db.query(PlayerEmploymentState)
        .filter(PlayerEmploymentState.player_id == player_id)
        .first()
    )


def _get_loan_accounts(db: Session, player_id: UUID) -> list[PlayerLoanAccount]:
    return (
        db.query(PlayerLoanAccount)
        .filter(
            PlayerLoanAccount.player_id == player_id,
            PlayerLoanAccount.days_remaining > 0,
        )
        .all()
    )


def _get_business(db: Session, player_id: UUID) -> PlayerBusiness | None:
    return (
        db.query(PlayerBusiness)
        .filter(PlayerBusiness.player_id == player_id, PlayerBusiness.active_flag == True)  # noqa: E712
        .first()
    )


def _get_borrowing_state(db: Session, player_id: UUID) -> PlayerBorrowingState | None:
    return (
        db.query(PlayerBorrowingState)
        .filter(PlayerBorrowingState.player_id == player_id)
        .first()
    )


def _get_delinquency_state(db: Session, player_id: UUID) -> PlayerDelinquencyState | None:
    return (
        db.query(PlayerDelinquencyState)
        .filter(PlayerDelinquencyState.player_id == player_id)
        .first()
    )


# ---------------------------------------------------------------------------
# Obligation definition builders
# ---------------------------------------------------------------------------


def _build_obligation_definitions(
    player: Player,
    housing: PlayerHousingState | None,
    employment: PlayerEmploymentState | None,
    loans: list[PlayerLoanAccount],
    business: PlayerBusiness | None,
    day: int,
) -> list[dict]:
    """Return a sorted list of obligation/income definition dicts.

    Each dict has:
      key, family, obligation_type, amount_xgp, cycle_days, income_flag,
      source_loan_id (optional)
    """
    defs: list[dict] = []

    # --- personal housing obligations ---
    if housing is not None:
        rent_amount = _d(housing.monthly_housing_cost_xgp)
        if rent_amount <= 0:
            rent_amount = PLACEHOLDER_RENT_XGP
        defs.append({
            "key": "rent",
            "family": "personal",
            "obligation_type": "rent",
            "amount_xgp": rent_amount,
            "cycle_days": RENT_CYCLE,
            "income_flag": False,
            "source_loan_id": None,
        })

        util_amount = _d(housing.monthly_utilities_cost_xgp)
        if util_amount > 0:
            defs.append({
                "key": "utilities",
                "family": "personal",
                "obligation_type": "utilities",
                "amount_xgp": util_amount,
                "cycle_days": UTILITIES_CYCLE,
                "income_flag": False,
                "source_loan_id": None,
            })
        elif housing is not None:
            defs.append({
                "key": "utilities",
                "family": "personal",
                "obligation_type": "utilities",
                "amount_xgp": PLACEHOLDER_UTILITIES_XGP,
                "cycle_days": UTILITIES_CYCLE,
                "income_flag": False,
                "source_loan_id": None,
            })

        # insurance (approximated as 12% of monthly rent)
        insurance_amount = (rent_amount * Decimal("0.12")).quantize(Q2, rounding=ROUND_HALF_UP)
        if insurance_amount > 0:
            defs.append({
                "key": "insurance",
                "family": "personal",
                "obligation_type": "insurance",
                "amount_xgp": insurance_amount,
                "cycle_days": INSURANCE_CYCLE,
                "income_flag": False,
                "source_loan_id": None,
            })

    # Phone plan (everyone has one)
    defs.append({
        "key": "phone_plan",
        "family": "personal",
        "obligation_type": "phone",
        "amount_xgp": PLACEHOLDER_PHONE_XGP,
        "cycle_days": PHONE_CYCLE,
        "income_flag": False,
        "source_loan_id": None,
    })

    # --- debt obligations ---
    for loan in loans:
        if not hasattr(loan, "id") or loan.id is None:
            continue
        loan_key = f"loan_{str(loan.id)[:8]}"
        # daily payment × cycle: use 30-day amounts for monthly billing rhythm
        daily_pmt = _d(getattr(loan, "scheduled_daily_payment_xgp", 0))
        cycle = min(int(getattr(loan, "term_days", 30) or 30), 30)
        amount = (daily_pmt * Decimal(str(cycle))).quantize(Q2, rounding=ROUND_HALF_UP)
        if amount <= 0:
            continue
        defs.append({
            "key": loan_key,
            "family": "debt",
            "obligation_type": "loan_payment",
            "amount_xgp": amount,
            "cycle_days": cycle,
            "income_flag": False,
            "source_loan_id": loan.id,
        })

    # --- business overhead ---
    if business is not None:
        defs.append({
            "key": "business_overhead",
            "family": "business",
            "obligation_type": "overhead",
            "amount_xgp": PLACEHOLDER_OVERHEAD_XGP,
            "cycle_days": OVERHEAD_CYCLE,
            "income_flag": False,
            "source_loan_id": None,
        })

    # --- income arrivals ---
    if employment is not None:
        monthly_pay = _d(getattr(employment, "monthly_pay_xgp", 0))
        employed = getattr(employment, "employed_flag", False)
        if employed and monthly_pay > 0:
            # Biweekly if pay cadence stored, else monthly
            cadence = SALARY_CYCLE_BIWEEKLY if monthly_pay < Decimal("1500") else SALARY_CYCLE_DEFAULT
            pay_per_cycle = monthly_pay if cadence == SALARY_CYCLE_DEFAULT else (monthly_pay / Decimal("2")).quantize(Q2, rounding=ROUND_HALF_UP)
            defs.append({
                "key": "salary",
                "family": "income",
                "obligation_type": "salary",
                "amount_xgp": pay_per_cycle,
                "cycle_days": cadence,
                "income_flag": True,
                "source_loan_id": None,
            })

    if business is not None:
        biz_monthly = _d(getattr(business, "monthly_revenue_xgp", 0)) if hasattr(business, "monthly_revenue_xgp") else Decimal("0")
        if biz_monthly <= 0:
            # Use a proxy via daily_revenue if that column exists
            biz_monthly = _d(getattr(business, "daily_revenue_xgp", 0)) * 30 if hasattr(business, "daily_revenue_xgp") else Decimal("500")
        payout = (biz_monthly * Decimal("0.6")).quantize(Q2, rounding=ROUND_HALF_UP)
        defs.append({
            "key": "business_payout",
            "family": "income",
            "obligation_type": "business_payout",
            "amount_xgp": payout,
            "cycle_days": BUSINESS_PAYOUT_CYCLE,
            "income_flag": True,
            "source_loan_id": None,
        })

    return defs


def _compute_first_due_on(day: int, obligation_key: str, cycle_days: int) -> int:
    """Compute the first due-on day for a contract starting from `day`.

    Due dates are staggered deterministically by obligation_key hash so that
    rent/utilities/insurance don't all fall on the same day by default.
    This mirrors the player's real-world staggered bill arrival.
    """
    # Stagger offset: 0-5 days based on key hash, never the same day if possible
    offset = (hash(obligation_key) % max(1, cycle_days // 6))
    offset = abs(offset) % min(6, cycle_days)
    first_due = day + offset + 1  # minimum 1 day ahead
    return first_due


# ---------------------------------------------------------------------------
# Scoring helpers
# ---------------------------------------------------------------------------


def _compute_contract_density_score(
    events_in_window: list[PlayerContractEvent],
    window_days: int = 7,
) -> Decimal:
    """Return a 0–100 density score reflecting how clustered obligations are.

    Higher = more clustered (worse timing spread).
    """
    obligations = [e for e in events_in_window if not e.income_flag]
    if not obligations:
        return Decimal("10")   # very spread / no obligations = low density

    total = len(obligations)
    if total == 1:
        return Decimal("10")

    # Build day-bucket counts
    day_buckets: dict[int, int] = {}
    for ev in obligations:
        bucket = (ev.due_on_day // 3) * 3  # 3-day buckets
        day_buckets[bucket] = day_buckets.get(bucket, 0) + 1

    max_bucket = max(day_buckets.values())
    cluster_ratio = Decimal(str(max_bucket)) / Decimal(str(total))

    # Low clustering: cluster_ratio close to 1/total (perfectly spread)
    # High clustering: cluster_ratio approaching 1.0 (all on same day)
    baseline_ratio = Decimal("1") / Decimal(str(max(total, 1)))
    excess = _clamp(cluster_ratio - baseline_ratio, Decimal("0"), Decimal("1"))
    score = _clamp(excess * Decimal("120"), Decimal("0"), Decimal("100"))
    return _q4(score)


def _compute_timing_stability_score(
    density_score: Decimal,
    cash_gap: Decimal,
    days_to_next_income: int | None,
    employment_active: bool,
) -> Decimal:
    """Return a 0–100 stability score. Higher = more stable timing."""
    base = Decimal("80")
    base -= _clamp(density_score / Decimal("4"), Decimal("0"), Decimal("25"))

    if cash_gap > 0:
        penalty = _clamp(cash_gap / Decimal("500") * Decimal("15"), Decimal("0"), Decimal("20"))
        base -= penalty

    if days_to_next_income is None:
        base -= Decimal("10")
    elif days_to_next_income > 21:
        base -= Decimal("8")
    elif days_to_next_income > 14:
        base -= Decimal("4")

    if not employment_active:
        base -= Decimal("10")

    return _q4(_clamp(base))


def _clustering_label(density_score: Decimal) -> str:
    if density_score >= CLUSTER_HEAVY:
        return "heavily_clustered"
    if density_score >= CLUSTER_MODERATE:
        return "clustered"
    if density_score >= CLUSTER_MILD:
        return "mild_cluster"
    return "spread"


def _timing_pressure_label(density_score: Decimal) -> str:
    if density_score >= PRESSURE_ELEVATED_THRESHOLD:
        return "severe"
    if density_score >= PRESSURE_MANAGEABLE_THRESHOLD:
        return "elevated"
    if density_score >= PRESSURE_LOW_THRESHOLD:
        return "manageable"
    return "low"


def _bridge_need_label(
    cash_gap: Decimal,
    days_to_income: int | None,
    timing_pressure: str,
) -> str:
    if cash_gap <= 0:
        return "none"
    if cash_gap >= BRIDGE_URGENT_THRESHOLD:
        return "urgent"
    if cash_gap >= BRIDGE_MODERATE_THRESHOLD:
        if timing_pressure in ("elevated", "severe"):
            return "moderate"
        return "pre_payday_squeeze"
    if cash_gap >= BRIDGE_MINOR_THRESHOLD:
        if days_to_income is not None and days_to_income <= 3:
            return "pre_payday_squeeze"
        return "none"
    return "none"


def _obligation_collision_label(
    events_in_3d: list[PlayerContractEvent],
) -> str:
    obligations = [e for e in events_in_3d if not e.income_flag]
    cnt = len(obligations)
    if cnt >= 4:
        return "compound"
    if cnt == 3:
        return "collision"
    if cnt == 2:
        return "overlap"
    return "none"


# ---------------------------------------------------------------------------
# Cash gap computation
# ---------------------------------------------------------------------------


def _compute_cash_gap(
    player: Player,
    obligation_events: list[PlayerContractEvent],
    days_to_next_income: int | None,
    day: int,
) -> Decimal:
    """Return the expected cash shortfall before the next income event.

    Positive value → gap (bridge borrow might be rational).
    Zero/negative → sufficient cash.
    """
    cash = _d(getattr(player, "cash", 0))
    if days_to_next_income is None:
        window_days = 14
    else:
        window_days = days_to_next_income

    due_before_income = [
        e for e in obligation_events
        if not e.income_flag
        and e.due_on_day >= day
        and e.due_on_day <= day + window_days
        and e.status in ("upcoming", "due")
    ]
    total_due = sum(_d(e.amount_xgp) for e in due_before_income)
    gap = total_due - cash
    return _q4(max(Decimal("0"), gap))


# ---------------------------------------------------------------------------
# Core public functions
# ---------------------------------------------------------------------------


def generate_recurring_contracts(
    db: Session,
    player_id: str | UUID,
    day: int | None = None,
) -> dict:
    """Generate (or refresh) the forward obligation/income event rows.

    Creates PlayerContractEvent rows for the forward EVENT_FORWARD_WINDOW days.
    Uses ON CONFLICT upsert semantics (by obligation_key + due_on_day) so safe
    to call repeatedly without duplicating rows.

    Returns a summary dict with count of rows created/updated, obligation families.
    """
    current_day, current_date = _resolve_day(day)
    player = _get_player(db, player_id)
    pid = player.id

    housing = _get_housing_state(db, pid)
    employment = _get_employment_state(db, pid)
    loans = _get_loan_accounts(db, pid)
    business = _get_business(db, pid)

    obligation_defs = _build_obligation_definitions(
        player, housing, employment, loans, business, current_day
    )

    upserted = 0
    families_seen: set[str] = set()

    for odef in obligation_defs:
        families_seen.add(odef["family"])
        first_due = _compute_first_due_on(current_day, odef["key"], odef["cycle_days"])
        # Generate event for each cycle in forward window
        due = first_due
        while due <= current_day + EVENT_FORWARD_WINDOW:
            due_date = _day_to_date(due)
            existing = (
                db.query(PlayerContractEvent)
                .filter(
                    PlayerContractEvent.player_id == pid,
                    PlayerContractEvent.obligation_key == odef["key"],
                    PlayerContractEvent.due_on_day == due,
                )
                .first()
            )
            if existing is None:
                ev = PlayerContractEvent(
                    player_id=pid,
                    obligation_key=odef["key"],
                    obligation_family=odef["family"],
                    obligation_type=odef["obligation_type"],
                    amount_xgp=odef["amount_xgp"],
                    cycle_days=odef["cycle_days"],
                    due_on_day=due,
                    due_on_date=due_date,
                    status="upcoming",
                    income_flag=odef["income_flag"],
                    source_loan_id=odef.get("source_loan_id"),
                )
                db.add(ev)
                upserted += 1
            else:
                # Refresh amount in case player's contract costs changed
                # but only if status is still upcoming
                if existing.status == "upcoming":
                    existing.amount_xgp = odef["amount_xgp"]
                    upserted += 1
            due += odef["cycle_days"]

    db.flush()

    return {
        "player_id": str(pid),
        "day": current_day,
        "event_rows_upserted": upserted,
        "obligation_families": sorted(list(families_seen)),
        "obligation_definitions": len(obligation_defs),
    }


def apply_contract_cycle_progression(
    db: Session,
    player_id: str | UUID,
    day: int | None = None,
) -> dict:
    """Advance event statuses based on current game day.

    - upcoming events on/before today → status = "due"
    - due events more than 2 days past due (and not income) → status = "late"
    - Prune very old resolved events beyond backward-prune window

    Returns dict with counts of transitions made.
    """
    current_day, _ = _resolve_day(day)
    player = _get_player(db, player_id)
    pid = player.id

    to_due = (
        db.query(PlayerContractEvent)
        .filter(
            PlayerContractEvent.player_id == pid,
            PlayerContractEvent.status == "upcoming",
            PlayerContractEvent.due_on_day <= current_day,
            PlayerContractEvent.income_flag == False,  # noqa: E712
        )
        .all()
    )
    became_due = 0
    for ev in to_due:
        ev.status = "due"
        became_due += 1

    # Income events: mark paid automatically when past due (income arrives)
    income_due = (
        db.query(PlayerContractEvent)
        .filter(
            PlayerContractEvent.player_id == pid,
            PlayerContractEvent.status == "upcoming",
            PlayerContractEvent.due_on_day <= current_day,
            PlayerContractEvent.income_flag == True,  # noqa: E712
        )
        .all()
    )
    income_received = 0
    for ev in income_due:
        ev.status = "paid"
        ev.paid_on_day = current_day
        ev.paid_amount_xgp = ev.amount_xgp
        ev.resolution_note = "income_auto_received"
        income_received += 1

    became_late = 0
    late_threshold_day = current_day - 2
    to_late = (
        db.query(PlayerContractEvent)
        .filter(
            PlayerContractEvent.player_id == pid,
            PlayerContractEvent.status == "due",
            PlayerContractEvent.due_on_day <= late_threshold_day,
            PlayerContractEvent.income_flag == False,  # noqa: E712
        )
        .all()
    )
    for ev in to_late:
        ev.status = "late"
        became_late += 1

    db.flush()

    return {
        "player_id": str(pid),
        "day": current_day,
        "became_due": became_due,
        "became_late": became_late,
        "income_received": income_received,
    }


def build_upcoming_obligation_window(
    db: Session,
    player_id: str | UUID,
    day: int | None = None,
) -> dict:
    """Return the upcoming obligation/income events in 1d / 3d / 7d windows.

    Does NOT write to DB — pure read.
    """
    current_day, current_date = _resolve_day(day)
    player = _get_player(db, player_id)
    pid = player.id

    all_events = (
        db.query(PlayerContractEvent)
        .filter(
            PlayerContractEvent.player_id == pid,
            PlayerContractEvent.due_on_day >= current_day,
            PlayerContractEvent.due_on_day <= current_day + DUE_7D_WINDOW,
            PlayerContractEvent.status.in_(["upcoming", "due"]),
        )
        .order_by(PlayerContractEvent.due_on_day)
        .all()
    )

    def _fmt(ev: PlayerContractEvent) -> dict:
        return {
            "obligation_key": ev.obligation_key,
            "obligation_type": ev.obligation_type,
            "family": ev.obligation_family,
            "amount_xgp": float(ev.amount_xgp),
            "due_on_day": ev.due_on_day,
            "status": ev.status,
            "income_flag": ev.income_flag,
        }

    due_today = [_fmt(e) for e in all_events if e.due_on_day == current_day]
    due_3d = [_fmt(e) for e in all_events if current_day < e.due_on_day <= current_day + DUE_3D_WINDOW]
    due_7d = [_fmt(e) for e in all_events if current_day + DUE_3D_WINDOW < e.due_on_day <= current_day + DUE_7D_WINDOW]

    outflows_today = sum(e["amount_xgp"] for e in due_today if not e["income_flag"])
    outflows_3d = sum(e["amount_xgp"] for e in due_today + due_3d if not e["income_flag"])
    outflows_7d = sum(e["amount_xgp"] for e in due_today + due_3d + due_7d if not e["income_flag"])
    inflows_7d = sum(e["amount_xgp"] for e in due_today + due_3d + due_7d if e["income_flag"])

    return {
        "player_id": str(pid),
        "day": current_day,
        "due_today": due_today,
        "due_in_3d": due_3d,
        "due_in_7d": due_7d,
        "outflows_due_today_xgp": round(outflows_today, 4),
        "outflows_due_3d_xgp": round(outflows_3d, 4),
        "outflows_due_7d_xgp": round(outflows_7d, 4),
        "inflows_expected_7d_xgp": round(inflows_7d, 4),
        "net_7d_xgp": round(inflows_7d - outflows_7d, 4),
    }


def build_cash_timing_pressure_state(
    db: Session,
    player_id: str | UUID,
    day: int | None = None,
) -> dict:
    """Compute the cash-flow timing pressure state for this player on `day`.

    Pure read — does not persist.
    """
    current_day, current_date = _resolve_day(day)
    player = _get_player(db, player_id)
    pid = player.id

    # Get next 7d events for density scoring
    window_events = (
        db.query(PlayerContractEvent)
        .filter(
            PlayerContractEvent.player_id == pid,
            PlayerContractEvent.due_on_day >= current_day,
            PlayerContractEvent.due_on_day <= current_day + DUE_7D_WINDOW,
            PlayerContractEvent.status.in_(["upcoming", "due"]),
        )
        .all()
    )

    # Find next income event
    next_income_ev = (
        db.query(PlayerContractEvent)
        .filter(
            PlayerContractEvent.player_id == pid,
            PlayerContractEvent.income_flag == True,  # noqa: E712
            PlayerContractEvent.due_on_day >= current_day,
            PlayerContractEvent.status.in_(["upcoming", "due"]),
        )
        .order_by(PlayerContractEvent.due_on_day)
        .first()
    )

    days_to_income = None
    next_income_day = None
    next_income_type = None
    if next_income_ev is not None:
        days_to_income = next_income_ev.due_on_day - current_day
        next_income_day = next_income_ev.due_on_day
        next_income_type = next_income_ev.obligation_type

    # Next major obligation
    next_major_ev = (
        db.query(PlayerContractEvent)
        .filter(
            PlayerContractEvent.player_id == pid,
            PlayerContractEvent.income_flag == False,  # noqa: E712
            PlayerContractEvent.obligation_family.in_(list(MAJOR_OBLIGATION_FAMILIES)),
            PlayerContractEvent.due_on_day >= current_day,
            PlayerContractEvent.status.in_(["upcoming", "due"]),
        )
        .order_by(PlayerContractEvent.due_on_day)
        .first()
    )

    days_to_major = None
    next_major_day = None
    next_major_type = None
    if next_major_ev is not None:
        days_to_major = next_major_ev.due_on_day - current_day
        next_major_day = next_major_ev.due_on_day
        next_major_type = next_major_ev.obligation_type

    # Density score
    density_score = _compute_contract_density_score(window_events)

    # Cash gap
    cash_gap = _compute_cash_gap(player, window_events, days_to_income, current_day)

    employment = _get_employment_state(db, pid)
    employed = bool(getattr(employment, "employed_flag", False)) if employment else False
    stability_score = _compute_timing_stability_score(
        density_score, cash_gap, days_to_income, employed
    )

    t_label = _timing_pressure_label(density_score)
    c_label = _clustering_label(density_score)
    b_label = _bridge_need_label(cash_gap, days_to_income, t_label)

    events_3d = [e for e in window_events if e.due_on_day <= current_day + 3]
    coll_label = _obligation_collision_label(events_3d)

    # Detect false payday pressure: temporary squeeze before reliable income
    false_payday = (
        b_label in ("pre_payday_squeeze", "moderate")
        and days_to_income is not None
        and days_to_income <= 7
        and t_label in ("elevated", "severe")
    )

    return {
        "player_id": str(pid),
        "day": current_day,
        "cash_on_hand_xgp": float(_d(getattr(player, "cash", 0))),
        "cash_gap_before_next_income_xgp": float(cash_gap),
        "contract_density_score": float(density_score),
        "timing_stability_score": float(stability_score),
        "timing_pressure_label": t_label,
        "clustering_label": c_label,
        "bridge_need_label": b_label,
        "obligation_collision_label": coll_label,
        "false_payday_pressure": false_payday,
        "next_income_on": next_income_day,
        "next_income_type": next_income_type,
        "days_to_next_income": days_to_income,
        "next_major_due_on": next_major_day,
        "next_major_due_type": next_major_type,
        "days_to_next_major_due": days_to_major,
    }


def build_player_contract_schedule(
    db: Session,
    player_id: str | UUID,
    day: int | None = None,
) -> dict:
    """Build and persist the PlayerContractSchedule rolling snapshot for this player.

    Combines generate_recurring_contracts + apply_contract_cycle_progression +
    build_cash_timing_pressure_state into a persisted state row.

    Returns serializable dict of the persisted schedule state.
    """
    current_day, current_date = _resolve_day(day)
    player = _get_player(db, player_id)
    pid = player.id

    # Generate/refresh events
    gen_result = generate_recurring_contracts(db, pid, current_day)
    # Advance event statuses
    apply_contract_cycle_progression(db, pid, current_day)
    # Compute timing pressure
    pressure = build_cash_timing_pressure_state(db, pid, current_day)

    # Build the obligation map for JSON storage
    obligation_events_ahead = (
        db.query(PlayerContractEvent)
        .filter(
            PlayerContractEvent.player_id == pid,
            PlayerContractEvent.due_on_day >= current_day,
            PlayerContractEvent.due_on_day <= current_day + EVENT_FORWARD_WINDOW,
        )
        .order_by(PlayerContractEvent.due_on_day)
        .all()
    )

    obligation_map: dict[str, dict] = {}
    for ev in obligation_events_ahead:
        if ev.obligation_key not in obligation_map:
            obligation_map[ev.obligation_key] = {
                "amount_xgp": float(ev.amount_xgp),
                "cycle_days": ev.cycle_days,
                "next_due_on": ev.due_on_day,
                "family": ev.obligation_family,
                "income_flag": ev.income_flag,
            }

    income_events_ahead = [e for e in obligation_events_ahead if e.income_flag]
    income_cadence: dict[str, dict] = {}
    for ev in income_events_ahead:
        if ev.obligation_key not in income_cadence:
            income_cadence[ev.obligation_key] = {
                "amount_xgp": float(ev.amount_xgp),
                "cycle_days": ev.cycle_days,
                "next_pay_on": ev.due_on_day,
            }

    # Due-soon window snapshot
    due_window = {
        "due_today": [],
        "due_in_3d": [],
        "due_in_7d": [],
    }
    for ev in obligation_events_ahead:
        if ev.due_on_day == current_day:
            due_window["due_today"].append(ev.obligation_key)
        elif ev.due_on_day <= current_day + 3:
            due_window["due_in_3d"].append(ev.obligation_key)
        elif ev.due_on_day <= current_day + 7:
            due_window["due_in_7d"].append(ev.obligation_key)

    total_due_7d = sum(
        _d(e.amount_xgp)
        for e in obligation_events_ahead
        if not e.income_flag and e.due_on_day <= current_day + 7
    )
    active_contract_count = len(
        {e.obligation_key for e in obligation_events_ahead if not e.income_flag}
    )

    debug_payload = {
        "gen_result": gen_result,
        "obligation_families": gen_result["obligation_families"],
        "window_event_count": len(obligation_events_ahead),
    }

    # Upsert PlayerContractSchedule
    schedule = (
        db.query(PlayerContractSchedule)
        .filter(PlayerContractSchedule.player_id == pid)
        .first()
    )
    if schedule is None:
        schedule = PlayerContractSchedule(player_id=pid)
        db.add(schedule)

    schedule.active_contract_count = active_contract_count
    schedule.total_due_7d_xgp = _q4(total_due_7d)
    schedule.clustering_label = pressure["clustering_label"]
    schedule.next_major_due_on = pressure["next_major_due_on"]
    schedule.next_major_due_type = pressure["next_major_due_type"]
    schedule.days_to_next_major_due = pressure["days_to_next_major_due"]
    schedule.next_income_on = pressure["next_income_on"]
    schedule.next_income_type = pressure["next_income_type"]
    schedule.days_to_next_income = pressure["days_to_next_income"]
    schedule.contract_density_score = _q4(Decimal(str(pressure["contract_density_score"])))
    schedule.timing_stability_score = _q4(Decimal(str(pressure["timing_stability_score"])))
    schedule.cash_gap_before_next_income_xgp = _q4(Decimal(str(pressure["cash_gap_before_next_income_xgp"])))
    schedule.timing_pressure_label = pressure["timing_pressure_label"]
    schedule.bridge_need_label = pressure["bridge_need_label"]
    schedule.obligation_collision_label = pressure["obligation_collision_label"]
    schedule.false_payday_pressure = bool(pressure["false_payday_pressure"])
    schedule.recurring_obligation_map_json = _dump_json(obligation_map)
    schedule.income_cadence_json = _dump_json(income_cadence)
    schedule.due_window_json = _dump_json(due_window)
    schedule.debug_json = _dump_json(debug_payload)
    schedule.last_updated_on = current_day
    schedule.last_updated_date = current_date

    db.flush()

    return {
        "player_id": str(pid),
        "day": current_day,
        "active_contract_count": schedule.active_contract_count,
        "total_due_7d_xgp": float(schedule.total_due_7d_xgp),
        "clustering_label": schedule.clustering_label,
        "next_major_due_on": schedule.next_major_due_on,
        "next_major_due_type": schedule.next_major_due_type,
        "days_to_next_major_due": schedule.days_to_next_major_due,
        "next_income_on": schedule.next_income_on,
        "next_income_type": schedule.next_income_type,
        "days_to_next_income": schedule.days_to_next_income,
        "contract_density_score": float(schedule.contract_density_score),
        "timing_stability_score": float(schedule.timing_stability_score),
        "cash_gap_before_next_income_xgp": float(schedule.cash_gap_before_next_income_xgp),
        "timing_pressure_label": schedule.timing_pressure_label,
        "bridge_need_label": schedule.bridge_need_label,
        "obligation_collision_label": schedule.obligation_collision_label,
        "false_payday_pressure": schedule.false_payday_pressure,
        "recurring_obligation_map": obligation_map,
        "income_cadence": income_cadence,
        "due_window": due_window,
    }


def build_due_soon_summary(
    db: Session,
    player_id: str | UUID,
    day: int | None = None,
) -> dict:
    """Return a concise due-soon summary: what's coming up in the next 7 days.

    Pure read — does not persist.
    """
    current_day, _ = _resolve_day(day)
    player = _get_player(db, player_id)
    pid = player.id

    window_events = (
        db.query(PlayerContractEvent)
        .filter(
            PlayerContractEvent.player_id == pid,
            PlayerContractEvent.due_on_day >= current_day,
            PlayerContractEvent.due_on_day <= current_day + DUE_7D_WINDOW,
            PlayerContractEvent.status.in_(["upcoming", "due"]),
        )
        .order_by(PlayerContractEvent.due_on_day)
        .all()
    )

    obligations = [e for e in window_events if not e.income_flag]
    income_events = [e for e in window_events if e.income_flag]

    total_due = sum(_d(e.amount_xgp) for e in obligations)
    total_incoming = sum(_d(e.amount_xgp) for e in income_events)
    cash = _d(getattr(player, "cash", 0))

    items = [
        {
            "key": ev.obligation_key,
            "type": ev.obligation_type,
            "family": ev.obligation_family,
            "amount_xgp": float(ev.amount_xgp),
            "due_on_day": ev.due_on_day,
            "days_away": ev.due_on_day - current_day,
            "income_flag": ev.income_flag,
            "status": ev.status,
        }
        for ev in window_events
    ]

    return {
        "player_id": str(pid),
        "day": current_day,
        "cash_on_hand_xgp": float(cash),
        "total_due_7d_xgp": float(total_due),
        "total_income_expected_7d_xgp": float(total_incoming),
        "projected_net_xgp": float(cash + total_incoming - total_due),
        "item_count": len(items),
        "items": items,
    }


def build_contract_pressure_summary(
    db: Session,
    player_id: str | UUID,
    day: int | None = None,
) -> dict:
    """Full contract pressure summary — all signals in one dict.

    Pure read — does not persist.  Aggregates upcoming window,
    cash timing pressure, and late events into one comprehensive output.
    """
    current_day, _ = _resolve_day(day)
    player = _get_player(db, player_id)
    pid = player.id

    upcoming = build_upcoming_obligation_window(db, pid, current_day)
    pressure = build_cash_timing_pressure_state(db, pid, current_day)
    due_soon = build_due_soon_summary(db, pid, current_day)

    # Late events count
    late_count = (
        db.query(PlayerContractEvent)
        .filter(
            PlayerContractEvent.player_id == pid,
            PlayerContractEvent.status == "late",
        )
        .count()
    )

    delinquency = _get_delinquency_state(db, pid)
    delinquency_stage = getattr(delinquency, "stage", "current") if delinquency else "current"

    # Bridge borrow rationality:
    # Rational only when timing_pressure ≥ elevated AND delinquency not yet critical
    bridge_rational = (
        pressure["bridge_need_label"] in ("pre_payday_squeeze", "moderate", "urgent")
        and delinquency_stage not in ("critical", "delinquent")
        and pressure["false_payday_pressure"]
    )

    return {
        "player_id": str(pid),
        "day": current_day,
        # --- timing pressure ---
        "timing_pressure_label": pressure["timing_pressure_label"],
        "clustering_label": pressure["clustering_label"],
        "bridge_need_label": pressure["bridge_need_label"],
        "obligation_collision_label": pressure["obligation_collision_label"],
        "contract_density_score": pressure["contract_density_score"],
        "timing_stability_score": pressure["timing_stability_score"],
        "false_payday_pressure": pressure["false_payday_pressure"],
        # --- cash position ---
        "cash_on_hand_xgp": pressure["cash_on_hand_xgp"],
        "cash_gap_before_next_income_xgp": pressure["cash_gap_before_next_income_xgp"],
        # --- upcoming ---
        "outflows_due_today_xgp": upcoming["outflows_due_today_xgp"],
        "outflows_due_3d_xgp": upcoming["outflows_due_3d_xgp"],
        "outflows_due_7d_xgp": upcoming["outflows_due_7d_xgp"],
        "inflows_expected_7d_xgp": upcoming["inflows_expected_7d_xgp"],
        "net_7d_xgp": upcoming["net_7d_xgp"],
        # --- income timing ---
        "next_income_on": pressure["next_income_on"],
        "next_income_type": pressure["next_income_type"],
        "days_to_next_income": pressure["days_to_next_income"],
        # --- next major obligation ---
        "next_major_due_on": pressure["next_major_due_on"],
        "next_major_due_type": pressure["next_major_due_type"],
        "days_to_next_major_due": pressure["days_to_next_major_due"],
        # --- risk signals ---
        "late_event_count": late_count,
        "delinquency_stage": delinquency_stage,
        "bridge_borrow_is_rational": bridge_rational,
        # --- due soon items ---
        "due_soon_items": due_soon["items"],
    }
