"""Computed annual recap payloads for lifelong-run surfaces."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.daily_economy_event import DailyEconomyEvent
from app.models.daily_settlement_log import DailySettlementLog
from app.models.game_state import GameState
from app.models.gameplay_transaction import GameplayTransaction
from app.models.player import Player
from app.models.player_business import PlayerBusiness
from app.models.player_daily_state import PlayerDailyState
from app.models.player_housing import PlayerHousing
from app.models.player_net_worth_snapshot import PlayerNetWorthSnapshot
from app.models.player_progression_state import PlayerProgressionState

MONEY_Q = Decimal("0.01")
YEAR_ONE = 1
YEAR_ONE_DAYS = 365
DEBUG_PREVIEW_DAYS = 30


class AnnualRecapError(Exception):
    """Base annual recap exception."""


class AnnualRecapNotFoundError(AnnualRecapError):
    """Raised when a player cannot be found."""


class AnnualRecapUnavailableError(AnnualRecapError):
    """Raised when a recap is requested before the required day threshold."""


class AnnualRecapValidationError(AnnualRecapError):
    """Raised for unsupported recap request shapes."""


def _d(value: object) -> Decimal:
    return Decimal(str(value or 0))


def _money(value: object) -> Decimal:
    return _d(value).quantize(MONEY_Q, rounding=ROUND_HALF_UP)


def _money_float(value: object) -> float:
    return float(_money(value))


def _safe_int(value: object, fallback: int = 0) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return int(fallback)


def _resolve_player(db: Session, player_id: str | UUID) -> Player:
    try:
        pid = player_id if isinstance(player_id, UUID) else UUID(str(player_id))
    except ValueError as exc:
        raise AnnualRecapNotFoundError("Player not found.") from exc

    player = db.query(Player).filter(Player.id == pid).first()
    if player is None:
        raise AnnualRecapNotFoundError("Player not found.")
    return player


def annual_recap_title(net_worth_change: object, ending_net_worth: object) -> str:
    """Return the deterministic title for a year-end recap."""
    net_change = _money(net_worth_change)
    ending_value = _money(ending_net_worth)

    title = "Still Fighting" if net_change < Decimal("0.00") else "Survivor"
    if ending_value >= Decimal("10000.00"):
        title = "Survivor Turned Owner"
    if ending_value >= Decimal("50000.00"):
        title = "Independent Operator"
    if ending_value >= Decimal("100000.00"):
        title = "Financially Free"
    return title


def _current_player_day(db: Session, player: Player) -> int:
    candidates = [
        _safe_int(getattr(player, "last_settled_day", 0), 0),
        _safe_int(getattr(player, "run_end_day", 0), 0),
    ]

    max_daily_state_day = (
        db.query(func.max(PlayerDailyState.day_number))
        .filter(PlayerDailyState.player_id == player.id)
        .scalar()
    )
    max_settlement_day = (
        db.query(func.max(DailySettlementLog.day_number))
        .filter(DailySettlementLog.player_id == player.id)
        .scalar()
    )
    candidates.extend([
        _safe_int(max_daily_state_day, 0),
        _safe_int(max_settlement_day, 0),
    ])

    state = db.query(GameState).order_by(GameState.id.asc()).first()
    if state is not None:
        candidates.append(_safe_int(getattr(state, "current_day", 1), 1))

    return max(1, *candidates)


def _latest_snapshot_on_or_before(
    db: Session,
    player: Player,
    day_number: int,
) -> PlayerNetWorthSnapshot | None:
    return (
        db.query(PlayerNetWorthSnapshot)
        .filter(
            PlayerNetWorthSnapshot.player_id == player.id,
            PlayerNetWorthSnapshot.day <= int(day_number),
        )
        .order_by(PlayerNetWorthSnapshot.day.desc(), PlayerNetWorthSnapshot.created_at.desc())
        .first()
    )


def _snapshot_for_day(db: Session, player: Player, day_number: int) -> PlayerNetWorthSnapshot | None:
    return (
        db.query(PlayerNetWorthSnapshot)
        .filter(
            PlayerNetWorthSnapshot.player_id == player.id,
            PlayerNetWorthSnapshot.day == int(day_number),
        )
        .order_by(PlayerNetWorthSnapshot.created_at.desc())
        .first()
    )


def _active_business_count(db: Session, player: Player, recap_day: int) -> int:
    return _safe_int(
        db.query(func.count(PlayerBusiness.id))
        .filter(
            PlayerBusiness.player_id == player.id,
            PlayerBusiness.is_active.is_(True),
            PlayerBusiness.created_day <= int(recap_day),
        )
        .scalar(),
        0,
    )


def _land_owned_count(db: Session, player: Player, recap_day: int) -> int:
    return _safe_int(
        db.query(func.count(PlayerHousing.id))
        .filter(
            PlayerHousing.player_id == player.id,
            PlayerHousing.status == "active",
            PlayerHousing.occupancy_type == "own",
            PlayerHousing.move_in_day <= int(recap_day),
        )
        .scalar(),
        0,
    )


def _best_streak(db: Session, player: Player) -> int:
    row = (
        db.query(PlayerProgressionState)
        .filter(PlayerProgressionState.player_id == player.id)
        .first()
    )
    if row is None:
        return 0
    return max(
        _safe_int(getattr(row, "login_streak_best", 0), 0),
        _safe_int(getattr(row, "productive_day_streak_best", 0), 0),
        _safe_int(getattr(row, "positive_cash_flow_streak_best", 0), 0),
        _safe_int(getattr(row, "training_streak_best", 0), 0),
        _safe_int(getattr(row, "business_consistency_streak_best", 0), 0),
        _safe_int(getattr(row, "low_distress_streak_best", 0), 0),
    )


def _settlement_totals(db: Session, player: Player, recap_day: int) -> tuple[Decimal, Decimal, int]:
    rows = (
        db.query(
            func.coalesce(func.sum(DailySettlementLog.income_xgp), 0),
            func.coalesce(func.sum(DailySettlementLog.expenses_xgp), 0),
            func.count(DailySettlementLog.id),
        )
        .filter(
            DailySettlementLog.player_id == player.id,
            DailySettlementLog.day_number >= 1,
            DailySettlementLog.day_number <= int(recap_day),
        )
        .one()
    )
    income, expenses, row_count = rows
    return _money(income), _money(expenses), _safe_int(row_count, 0)


def _gameplay_transaction_totals(db: Session, player: Player, recap_day: int) -> tuple[Decimal, Decimal]:
    income = (
        db.query(func.coalesce(func.sum(GameplayTransaction.amount), 0))
        .filter(
            GameplayTransaction.player_id == player.id,
            GameplayTransaction.day >= 1,
            GameplayTransaction.day <= int(recap_day),
            GameplayTransaction.type == "income",
        )
        .scalar()
    )
    expense = (
        db.query(func.coalesce(func.sum(GameplayTransaction.amount), 0))
        .filter(
            GameplayTransaction.player_id == player.id,
            GameplayTransaction.day >= 1,
            GameplayTransaction.day <= int(recap_day),
            GameplayTransaction.type == "expense",
        )
        .scalar()
    )
    return _money(income), _money(expense)


def _latest_credit_score(db: Session, player: Player, recap_day: int) -> int:
    row = (
        db.query(DailySettlementLog)
        .filter(
            DailySettlementLog.player_id == player.id,
            DailySettlementLog.day_number <= int(recap_day),
        )
        .order_by(DailySettlementLog.day_number.desc(), DailySettlementLog.created_at.desc())
        .first()
    )
    if row is not None:
        return _safe_int(getattr(row, "credit_score_after", None), _safe_int(getattr(player, "credit_score", 650), 650))
    return _safe_int(getattr(player, "credit_score", 650), 650)


def _humanize_key(value: object) -> str:
    raw = str(value or "").strip()
    if not raw:
        return "business"
    return raw.replace("_", " ").replace("-", " ").lower()


def _biggest_win(
    db: Session,
    player: Player,
    *,
    recap_day: int,
    businesses_owned: int,
    net_worth_change: Decimal,
) -> str:
    if businesses_owned > 0:
        first_business = (
            db.query(PlayerBusiness)
            .filter(
                PlayerBusiness.player_id == player.id,
                PlayerBusiness.created_day <= int(recap_day),
            )
            .order_by(PlayerBusiness.created_day.asc(), PlayerBusiness.created_at.asc())
            .first()
        )
        label = _humanize_key(getattr(first_business, "business_id", None))
        return f"Opened your first {label}"
    if net_worth_change > Decimal("0.00"):
        return f"Grew net worth by {_money_float(net_worth_change):,.2f} XGP"
    return "Survived the year without a major win recorded"


def _biggest_loss(
    db: Session,
    player: Player,
    *,
    recap_day: int,
    total_income: Decimal,
    total_expenses: Decimal,
    debt: Decimal,
) -> str:
    missed_payment_count = _safe_int(
        db.query(func.count(DailySettlementLog.id))
        .filter(
            DailySettlementLog.player_id == player.id,
            DailySettlementLog.day_number <= int(recap_day),
            DailySettlementLog.debt_payment_missed.is_(True),
        )
        .scalar(),
        0,
    )
    if missed_payment_count > 0:
        return f"Missed {missed_payment_count} payment{'s' if missed_payment_count != 1 else ''} during Year 1"
    if total_expenses > total_income:
        return "Expenses outran income during the run"
    if debt > Decimal("0.00"):
        return f"Carried {_money_float(debt):,.2f} XGP debt into the recap"
    return "No major loss recorded"


def _top_event(db: Session, recap_day: int) -> str:
    event = (
        db.query(DailyEconomyEvent)
        .filter(DailyEconomyEvent.day <= int(recap_day))
        .order_by(DailyEconomyEvent.severity.desc(), DailyEconomyEvent.day.desc())
        .first()
    )
    if event is None:
        return "No major event recorded yet"
    return str(event.headline or event.summary or "No major event recorded yet")


def build_player_annual_recap(
    db: Session,
    player_id: str | UUID,
    *,
    year: int = YEAR_ONE,
    debug: bool = False,
) -> dict:
    """Build a read-only Year 1 recap payload for a player."""
    if int(year) != YEAR_ONE:
        raise AnnualRecapValidationError("Only Year 1 recap is available.")

    player = _resolve_player(db, player_id)
    current_day = _current_player_day(db, player)
    real_year_available = current_day >= YEAR_ONE_DAYS
    debug_available = bool(debug) and current_day >= DEBUG_PREVIEW_DAYS

    if not real_year_available and not debug_available:
        raise AnnualRecapUnavailableError(
            f"Year 1 recap is available at day {YEAR_ONE_DAYS}. Debug preview unlocks at day {DEBUG_PREVIEW_DAYS}."
        )

    recap_day = YEAR_ONE_DAYS if real_year_available else DEBUG_PREVIEW_DAYS

    starting_snapshot = _snapshot_for_day(db, player, 1)
    ending_snapshot = _latest_snapshot_on_or_before(db, player, recap_day)
    starting_net_worth = _money(getattr(starting_snapshot, "net_worth_xgp", 0) if starting_snapshot else 0)
    ending_net_worth = _money(
        getattr(ending_snapshot, "net_worth_xgp", None)
        if ending_snapshot is not None
        else getattr(player, "net_worth_xgp", getattr(player, "net_worth", 0))
    )
    net_worth_change = _money(ending_net_worth - starting_net_worth)

    cash = _money(
        getattr(ending_snapshot, "cash_xgp", None)
        if ending_snapshot is not None
        else getattr(player, "cash_xgp", getattr(player, "cash", 0))
    )
    debt = _money(
        getattr(ending_snapshot, "debt_xgp", None)
        if ending_snapshot is not None
        else getattr(player, "debt_xgp", 0)
    )

    total_income, total_expenses, settlement_count = _settlement_totals(db, player, recap_day)
    if settlement_count <= 0:
        total_income, total_expenses = _gameplay_transaction_totals(db, player, recap_day)

    businesses_owned = _active_business_count(db, player, recap_day)
    land_owned = _land_owned_count(db, player, recap_day)

    return {
        "year": YEAR_ONE,
        "days_survived": int(recap_day),
        "starting_net_worth": _money_float(starting_net_worth),
        "ending_net_worth": _money_float(ending_net_worth),
        "net_worth_change": _money_float(net_worth_change),
        "cash": _money_float(cash),
        "debt": _money_float(debt),
        "credit_score": _latest_credit_score(db, player, recap_day),
        "businesses_owned": businesses_owned,
        "land_owned": land_owned,
        "best_streak": _best_streak(db, player),
        "total_income": _money_float(total_income),
        "total_expenses": _money_float(total_expenses),
        "biggest_win": _biggest_win(
            db,
            player,
            recap_day=recap_day,
            businesses_owned=businesses_owned,
            net_worth_change=net_worth_change,
        ),
        "biggest_loss": _biggest_loss(
            db,
            player,
            recap_day=recap_day,
            total_income=total_income,
            total_expenses=total_expenses,
            debt=debt,
        ),
        "top_event": _top_event(db, recap_day),
        "title": annual_recap_title(net_worth_change, ending_net_worth),
    }
