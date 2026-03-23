"""Housing Engine — Step 7 (region cost layer) + Step 8 (property/debt system).

Step 7 functions (module-level, pure/stateless where possible):
  get_or_seed_default_housing_regions  — idempotent seed of suburban/downtown
  get_housing_region_by_id             — fetch one active HousingRegion
  calculate_daily_housing_cost         — cost float for a region
  calculate_housing_stress_modifier    — stress int for a region
  validate_housing_assignment          — guard valid region_id values
  apply_daily_housing_cost             — deduct XGP + create audit rows (no commit)

Step 8 class (HousingEngine):
  All legacy housing/property/debt logic lives in the class below.

Design rules (shared):
  - One active housing arrangement per player (enforced by HousingEngine).
  - Daily housing cost applied exactly once per in-game day.
  - All XGP mutations must be paired with an XGPTransaction ledger row.
  - Housing is the first fixed recurring cost layer — region choice matters.
  - Downtown offers more future opportunity but costs more and adds stress.
  - Suburban is cheaper and calmer — the safe social-mobility starting point.
  - This step bridges toward commute, opportunity, and networking systems.
"""

from __future__ import annotations

import random
import uuid as _uuid_mod
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.models.debt_account import DebtAccount
from app.models.economy import EconomyState
from app.models.game_state import GameState
from app.models.housing_action import HousingAction
from app.models.housing_daily_snapshot import HousingDailySnapshot
from app.models.housing_definition import HOUSING_CATALOG, HousingDefinition

# ─────────────────────────────────────────────────────────────────────────────
# Step 7 — Housing Region Cost Layer (standalone module-level functions)
# ─────────────────────────────────────────────────────────────────────────────

# Valid region identifiers for MVP.
_VALID_REGIONS = {"suburban", "downtown"}

# Unpaid housing stress penalties by region (applied when player cannot pay).
_UNPAID_STRESS_PENALTY: dict[str, int] = {
    "suburban": 3,
    "downtown": 5,
}


def get_or_seed_default_housing_regions(db: Session) -> list:
    """Ensure the default housing region rows exist and return active regions.

    Idempotent — safe to call on every startup.  If a region already exists
    (identified by region_id), its row is left unchanged.

    Returns the list of active HousingRegion objects.
    """
    from app.models.housing_region import HousingRegion, DEFAULT_HOUSING_REGIONS

    for seed in DEFAULT_HOUSING_REGIONS:
        existing = (
            db.query(HousingRegion)
            .filter(HousingRegion.region_id == seed["region_id"])
            .first()
        )
        if existing is None:
            db.add(HousingRegion(**seed))

    db.commit()

    return (
        db.query(HousingRegion)
        .filter(HousingRegion.is_active.is_(True))
        .order_by(HousingRegion.region_id)
        .all()
    )


def get_housing_region_by_id(db: Session, region_id: str):
    """Return the active HousingRegion for *region_id*, or None if not found."""
    from app.models.housing_region import HousingRegion

    return (
        db.query(HousingRegion)
        .filter(
            HousingRegion.region_id == region_id,
            HousingRegion.is_active.is_(True),
        )
        .first()
    )


def calculate_daily_housing_cost(region) -> float:
    """Return the daily XGP cost for *region*, rounded to 2 decimal places."""
    return round(float(region.daily_cost), 2)


def calculate_housing_stress_modifier(region) -> int:
    """Return the settlement stress modifier for *region*.

    Negative values calm the player (suburban = -1).
    Positive values add pressure (downtown = +2).
    """
    return int(region.stress_modifier)


def validate_housing_assignment(region_id: str) -> tuple[bool, str | None]:
    """Return (True, None) if *region_id* is a valid assignable region.

    For MVP only "suburban" and "downtown" are accepted.
    Returns (False, reason_string) for any invalid input.
    """
    if not region_id or not isinstance(region_id, str):
        return False, "region_id must be a non-empty string."
    if region_id not in _VALID_REGIONS:
        return False, (
            f"'{region_id}' is not a valid housing region. "
            f"Choose from: {', '.join(sorted(_VALID_REGIONS))}."
        )
    return True, None


def apply_daily_housing_cost(db: Session, player, day_number: int) -> dict:
    """Apply the daily housing cost for *player* on *day_number*.

    This function is designed to be called from within the settlement flow.
    It adds DB objects to the current session but does NOT commit — the
    caller (run_player_end_of_day_settlement) commits everything atomically.

    Logic:
      1. If player has no housing_region_id, return a zero-cost safe result.
      2. Fetch the active HousingRegion.
      3. Check if a HousingPayment already exists for this player/day
         (idempotency guard — prevents double-charging if called twice).
      4. If player.cash >= cost:
           - Deduct player.cash
           - Create HousingPayment row
           - Create XGPTransaction row (transaction_type="housing_cost", direction="out")
           - Return paid=True with the region's normal stress_modifier.
      5. If player.cash < cost:
           - Do NOT deduct anything.
           - Return paid=False with the unpaid stress penalty for the region.

    Return dict keys:
      region_id         str | None
      amount            float  (0 if no region or unpaid)
      paid              bool
      stress_modifier   int    (effective value already accounting for paid/unpaid)
    """
    from app.models.housing_region import HousingRegion
    from app.models.housing_payment import HousingPayment
    from app.models.xgp_transaction import XGPTransaction

    # ── 1. No region assigned → safe zero-cost pass-through ──────────────────
    region_id = getattr(player, "housing_region_id", None)
    if not region_id:
        return {"region_id": None, "amount": 0.0, "paid": False, "stress_modifier": 0}

    # ── 2. Fetch region ───────────────────────────────────────────────────────
    region = (
        db.query(HousingRegion)
        .filter(
            HousingRegion.region_id == region_id,
            HousingRegion.is_active.is_(True),
        )
        .first()
    )
    if region is None:
        # Region was deactivated; treat as no housing (safe degradation).
        return {"region_id": region_id, "amount": 0.0, "paid": False, "stress_modifier": 0}

    cost = calculate_daily_housing_cost(region)

    # ── 3. Idempotency guard — don't double-charge the same day ───────────────
    already_paid = (
        db.query(HousingPayment)
        .filter(
            HousingPayment.player_id == player.id,
            HousingPayment.day_number == day_number,
        )
        .first()
    )
    if already_paid:
        # Payment already processed for this day — return recorded values.
        return {
            "region_id": region_id,
            "amount": float(already_paid.amount),
            "paid": True,
            "stress_modifier": calculate_housing_stress_modifier(region),
        }

    balance_before = round(float(player.cash or 0), 4)

    # ── 4. Sufficient balance → deduct and record ─────────────────────────────
    if balance_before >= cost:
        balance_after = round(balance_before - cost, 4)

        player.cash = balance_after

        payment = HousingPayment(
            player_id=player.id,
            region_id=region_id,
            day_number=day_number,
            amount=cost,
            balance_before=balance_before,
            balance_after=balance_after,
        )
        db.add(payment)

        # Paired XGP ledger entry — housing is tracked same as any other outflow.
        txn = XGPTransaction(
            player_id=player.id,
            transaction_type="housing_cost",
            direction="out",
            amount=cost,
            balance_before=balance_before,
            balance_after=balance_after,
            reference_type="housing_payment",
            reference_id=str(payment.id),
            description=f"{region.display_name} daily housing cost",
        )
        db.add(txn)

        return {
            "region_id": region_id,
            "amount": cost,
            "paid": True,
            "stress_modifier": calculate_housing_stress_modifier(region),
        }

    # ── 5. Insufficient balance → penalty stress, no deduction ───────────────
    unpaid_penalty = _UNPAID_STRESS_PENALTY.get(region_id, 4)
    return {
        "region_id": region_id,
        "amount": 0.0,
        "paid": False,
        "stress_modifier": unpaid_penalty,  # larger penalty for missed payment
    }


from app.models.player import Player
from app.models.player_housing import PlayerHousing
from app.engine import housing_balance_engine as _balance

# ── Constants ─────────────────────────────────────────────────────────────────

_MORTGAGE_SPREAD = 1.5        # percentage points added to economy interest rate
_MORTGAGE_RATE_MIN = 3.0      # floor annual % for mortgage
_MORTGAGE_RATE_MAX = 12.0     # ceiling annual % for mortgage
_DOWN_PAYMENT_RATIO = 0.10    # 10% of estimated home value
_AMORTIZATION_DAYS = 30 * 365 # simplified 30-year mortgage period in days
_EMERGENCY_INTEREST_RATE = 15.0  # annual % on emergency debt
_MOVE_IN_BUFFER_DAYS = 3      # rent: upfront = N days of daily cost

_MAINTENANCE_CHANCE: dict[str, float] = {
    "low":         0.02,   # ~2% per day — rented/low-risk properties
    "medium":      0.06,   # ~6% per day — suburban owned
    "medium_high": 0.10,   # ~10% per day — downtown owned
}

# (tier_name, (min_cost, max_cost), probability_weight)
_MAINTENANCE_TIERS: list[tuple[str, tuple[int, int], float]] = [
    ("minor",  (15,  40),  0.60),
    ("medium", (50, 120),  0.30),
    ("major",  (150, 300), 0.10),  # rare
]

_CREDIT_SCORE_MIN = 300
_CREDIT_SCORE_MAX = 850
_HOUSING_STABILITY_MIN = 0
_HOUSING_STABILITY_MAX = 100

_D = Decimal


class HousingEngine:
    """Processes all player housing and debt actions for Gold Penny."""

    # ── Money helpers ─────────────────────────────────────────────────────────

    def _money(self, val: Any) -> Decimal:
        return Decimal(str(val)).quantize(_D("0.01"), rounding=ROUND_HALF_UP)

    # ── DB helpers ────────────────────────────────────────────────────────────

    def _get_current_day(self, db: Session) -> int:
        state = db.query(GameState).order_by(GameState.id.asc()).first()
        return int(state.current_day) if state else 1

    def _get_economy(self, db: Session) -> EconomyState | None:
        return db.query(EconomyState).order_by(EconomyState.day.desc()).first()

    def _get_active_housing(self, player: Player, db: Session) -> PlayerHousing | None:
        return (
            db.query(PlayerHousing)
            .filter(PlayerHousing.player_id == player.id, PlayerHousing.status == "active")
            .first()
        )

    # ── Mortgage calculations ─────────────────────────────────────────────────

    def _compute_mortgage_rate(self, economy: EconomyState | None) -> float:
        base = economy.interest_rate if economy else 4.5
        return float(max(_MORTGAGE_RATE_MIN, min(_MORTGAGE_RATE_MAX, base + _MORTGAGE_SPREAD)))

    def _compute_minimum_daily_payment(self, principal: float, annual_rate: float) -> Decimal:
        """Simplified daily payment: daily interest + fixed principal amortization."""
        daily_principal = principal / _AMORTIZATION_DAYS
        daily_interest = principal * (annual_rate / 100.0) / 365.0
        return self._money(daily_principal + daily_interest)

    # ── Maintenance ───────────────────────────────────────────────────────────

    def _maybe_trigger_maintenance(
        self, defn: HousingDefinition
    ) -> tuple[bool, float, str]:
        """Roll for a maintenance event. Returns (triggered, cost, note)."""
        # Only owned housing triggers meaningful maintenance
        if defn.occupancy_type != "own":
            return False, 0.0, ""
        chance = _MAINTENANCE_CHANCE.get(defn.maintenance_risk, 0.0)
        if random.random() > chance:
            return False, 0.0, ""
        # Weighted tier selection
        roll = random.random()
        cumulative = 0.0
        for tier_name, amount_range, weight in _MAINTENANCE_TIERS:
            cumulative += weight
            if roll <= cumulative:
                cost = random.randint(amount_range[0], amount_range[1])
                return True, float(cost), f"{tier_name.capitalize()} maintenance event"
        # Fallback
        return True, float(random.randint(15, 40)), "Minor maintenance event"

    # ── Delinquency helpers ───────────────────────────────────────────────────

    def _delinquency_from_count(self, count: int) -> str:
        if count == 0:
            return "current"
        elif count <= 2:
            return "late"
        elif count <= 5:
            return "delinquent"
        return "severe"

    # ── Clamping ──────────────────────────────────────────────────────────────

    def _clamp_credit(self, score: int) -> int:
        return max(_CREDIT_SCORE_MIN, min(_CREDIT_SCORE_MAX, score))

    def _clamp_stability(self, val: int) -> int:
        return max(_HOUSING_STABILITY_MIN, min(_HOUSING_STABILITY_MAX, val))

    def _clamp_stress(self, val: int) -> int:
        return max(0, min(100, val))

    # ── Net worth ─────────────────────────────────────────────────────────────

    def _update_net_worth(self, player: Player, db: Session) -> None:
        """Recalculate player net_worth = cash + home_equity (if owned)."""
        cash = float(player.cash)
        home_equity = 0.0
        owned = (
            db.query(PlayerHousing)
            .filter(
                PlayerHousing.player_id == player.id,
                PlayerHousing.status == "active",
                PlayerHousing.occupancy_type == "own",
            )
            .first()
        )
        if owned and owned.linked_debt_account_id:
            debt = (
                db.query(DebtAccount)
                .filter(DebtAccount.id == owned.linked_debt_account_id)
                .first()
            )
            if debt:
                raw_equity = float(owned.property_value or 0) - float(debt.principal_balance)
                home_equity = max(0.0, raw_equity)
        player.net_worth = float(self._money(cash + home_equity))

    # ── Serializers ───────────────────────────────────────────────────────────

    def _serialize_housing(self, housing: PlayerHousing) -> dict:
        return {
            "id": str(housing.id),
            "housing_key": housing.housing_key,
            "region": housing.region,
            "occupancy_type": housing.occupancy_type,
            "status": housing.status,
            "daily_cost": float(housing.daily_cost),
            "move_in_day": housing.move_in_day,
            "last_cost_applied_day": housing.last_cost_applied_day,
            "property_value": float(housing.property_value) if housing.property_value else None,
            "linked_debt_account_id": (
                str(housing.linked_debt_account_id) if housing.linked_debt_account_id else None
            ),
            # Step 8b cumulative tracking
            "affordability_pressure": float(housing.affordability_pressure or 1.0),
            "region_pressure_modifier": float(housing.region_pressure_modifier or 1.0),
            "cumulative_housing_paid": float(housing.cumulative_housing_paid or 0),
            "cumulative_property_tax_paid": float(housing.cumulative_property_tax_paid or 0),
            "cumulative_maintenance_paid": float(housing.cumulative_maintenance_paid or 0),
            "cumulative_debt_paid": float(housing.cumulative_debt_paid or 0),
            "consecutive_missed_housing_days": int(housing.consecutive_missed_housing_days or 0),
        }

    def _serialize_debt(self, debt: DebtAccount) -> dict:
        return {
            "id": str(debt.id),
            "debt_type": debt.debt_type,
            "principal_balance": float(debt.principal_balance),
            "interest_rate": debt.interest_rate,
            "minimum_daily_payment": float(debt.minimum_daily_payment),
            "missed_payment_count": debt.missed_payment_count,
            "delinquency_status": debt.delinquency_status,
            "penalty_rate_modifier": float(getattr(debt, "penalty_rate_modifier", 1.0) or 1.0),
            "consecutive_missed_payments": int(getattr(debt, "consecutive_missed_payments", 0) or 0),
            "cumulative_interest_paid": float(getattr(debt, "cumulative_interest_paid", 0) or 0),
            "cumulative_principal_paid": float(getattr(debt, "cumulative_principal_paid", 0) or 0),
            "originated_day": debt.originated_day,
            "last_payment_day": debt.last_payment_day,
        }

    # ── Missed payment penalties ──────────────────────────────────────────────

    def _apply_missed_payment_penalties(
        self,
        player: Player,
        debt: DebtAccount | None,
    ) -> int:
        """Increment debt miss count, degrade delinquency, penalise player.

        Returns the stress change to apply to the caller.
        """
        if debt:
            debt.missed_payment_count += 1
            debt.delinquency_status = self._delinquency_from_count(debt.missed_payment_count)
            count = debt.missed_payment_count
        else:
            count = 1

        if count <= 1:
            stress_penalty = 3
            credit_penalty = 5
            stability_penalty = 5
        elif count <= 3:
            stress_penalty = 6
            credit_penalty = 10
            stability_penalty = 8
        else:
            stress_penalty = 10
            credit_penalty = 20
            stability_penalty = 12

        player.credit_score = self._clamp_credit(player.credit_score - credit_penalty)
        player.housing_stability = self._clamp_stability(player.housing_stability - stability_penalty)
        return stress_penalty

    def _create_emergency_debt(
        self, player: Player, shortfall: float, current_day: int, db: Session
    ) -> None:
        """Add shortfall to an existing open emergency_debt, or create one."""
        existing = (
            db.query(DebtAccount)
            .filter(
                DebtAccount.player_id == player.id,
                DebtAccount.debt_type == "emergency_debt",
                DebtAccount.delinquency_status != "severe",
            )
            .first()
        )
        if existing:
            existing.principal_balance = self._money(
                float(existing.principal_balance) + shortfall
            )
        else:
            db.add(
                DebtAccount(
                    player_id=player.id,
                    debt_type="emergency_debt",
                    principal_balance=self._money(shortfall),
                    interest_rate=_EMERGENCY_INTEREST_RATE,
                    minimum_daily_payment=self._money(max(2.0, shortfall * 0.01)),
                    missed_payment_count=0,
                    delinquency_status="current",
                    originated_day=current_day,
                )
            )

    # ── Public API ────────────────────────────────────────────────────────────

    def list_housing_options(self) -> list[dict]:
        """Return all static housing definitions with computed move-in costs."""
        result = []
        for defn in HOUSING_CATALOG.values():
            entry: dict = {
                "housing_key": defn.housing_key,
                "display_name": defn.display_name,
                "region": defn.region,
                "occupancy_type": defn.occupancy_type,
                "daily_base_cost": defn.daily_base_cost,
                "estimated_home_value": defn.estimated_home_value,
                "stress_modifier": defn.stress_modifier,
                "opportunity_modifier": defn.opportunity_modifier,
                "commute_modifier": defn.commute_modifier,
                "property_tax_rate": defn.property_tax_rate,
                "maintenance_risk": defn.maintenance_risk,
            }
            if defn.occupancy_type == "own" and defn.estimated_home_value:
                entry["down_payment_required"] = round(
                    defn.estimated_home_value * _DOWN_PAYMENT_RATIO, 2
                )
                entry["move_in_cost"] = entry["down_payment_required"]
            else:
                entry["move_in_cost"] = round(defn.daily_base_cost * _MOVE_IN_BUFFER_DAYS, 2)
            result.append(entry)
        return result

    # ── Move-in ───────────────────────────────────────────────────────────────

    def move_into_housing(self, player: Player, housing_key: str, db: Session) -> dict:
        """Move a player into housing. Creates mortgage debt for ownership options."""
        if housing_key not in HOUSING_CATALOG:
            raise ValueError(f"Unknown housing_key: {housing_key!r}. "
                             f"Valid keys: {list(HOUSING_CATALOG)}")

        existing = self._get_active_housing(player, db)
        if existing:
            raise ValueError(
                "Player already has an active housing arrangement. "
                "You must move out before moving into new housing."
            )

        defn = HOUSING_CATALOG[housing_key]
        current_day = self._get_current_day(db)
        economy = self._get_economy(db)

        # ── Step 8b: Move cooldown — max one move per 3 in-game days ───────────────
        _MOVE_COOLDOWN_DAYS = 3
        recent_housing = (
            db.query(PlayerHousing)
            .filter(PlayerHousing.player_id == player.id)
            .order_by(PlayerHousing.move_in_day.desc())
            .first()
        )
        if recent_housing and (current_day - recent_housing.move_in_day) < _MOVE_COOLDOWN_DAYS:
            days_left = _MOVE_COOLDOWN_DAYS - (current_day - recent_housing.move_in_day)
            raise ValueError(
                f"Cannot switch housing more than once every {_MOVE_COOLDOWN_DAYS} in-game days. "
                f"Wait {days_left} more day(s)."
            )

        linked_debt_id = None
        property_value: Decimal | None = None
        mortgage_summary: dict | None = None

        if defn.occupancy_type == "rent":
            move_in_cost = self._money(defn.daily_base_cost * _MOVE_IN_BUFFER_DAYS)
            if float(player.cash) < float(move_in_cost):
                raise ValueError(
                    f"Insufficient cash. Moving in requires {float(move_in_cost):.2f} "
                    f"({_MOVE_IN_BUFFER_DAYS} days upfront). "
                    f"You have {float(player.cash):.2f}."
                )
            player.cash = self._money(float(player.cash) - float(move_in_cost))

        else:  # own
            home_value = defn.estimated_home_value  # guaranteed non-None for own
            down_payment = self._money(home_value * _DOWN_PAYMENT_RATIO)
            if float(player.cash) < float(down_payment):
                raise ValueError(
                    f"Insufficient cash for down payment. Required: {float(down_payment):.2f} "
                    f"(10% of {home_value:,.0f}). You have {float(player.cash):.2f}."
                )
            player.cash = self._money(float(player.cash) - float(down_payment))
            move_in_cost = down_payment
            property_value = self._money(home_value)

            # Mortgage debt
            mortgage_rate = self._compute_mortgage_rate(economy)
            principal = float(home_value) - float(down_payment)
            min_daily = self._compute_minimum_daily_payment(principal, mortgage_rate)

            debt = DebtAccount(
                player_id=player.id,
                debt_type="mortgage",
                principal_balance=self._money(principal),
                interest_rate=mortgage_rate,
                minimum_daily_payment=min_daily,
                missed_payment_count=0,
                delinquency_status="current",
                originated_day=current_day,
            )
            db.add(debt)
            db.flush()  # assign debt.id
            linked_debt_id = debt.id
            mortgage_summary = self._serialize_debt(debt)

        # Create housing record
        housing = PlayerHousing(
            player_id=player.id,
            housing_key=housing_key,
            region=defn.region,
            occupancy_type=defn.occupancy_type,
            status="active",
            daily_cost=self._money(defn.daily_base_cost),
            move_in_day=current_day,
            last_cost_applied_day=None,
            linked_debt_account_id=linked_debt_id,
            property_value=property_value,
        )
        db.add(housing)
        db.flush()

        # Update player
        player.region = defn.region
        player.has_active_housing = True
        self._update_net_worth(player, db)

        db.add(HousingAction(
            player_id=player.id,
            housing_id=housing.id,
            action_type="move_in",
            day=current_day,
            amount=move_in_cost,
            notes=f"Moved into {defn.display_name}",
        ))
        db.commit()
        db.refresh(player)

        result: dict = {
            "message": "Moved into housing",
            "housing_key": housing_key,
            "region": defn.region,
            "occupancy_type": defn.occupancy_type,
            "move_in_cost": float(move_in_cost),
            "cash_remaining": float(player.cash),
            "net_worth": float(player.net_worth),
        }
        if mortgage_summary:
            result["mortgage_rate_pct"] = self._compute_mortgage_rate(economy)
            result["mortgage"] = mortgage_summary
        return result

    # ── Current housing ───────────────────────────────────────────────────────

    def get_current_housing(self, player: Player, db: Session) -> dict | None:
        """Return the player's active housing with debt summary if owned."""
        housing = self._get_active_housing(player, db)
        if not housing:
            return None
        result = self._serialize_housing(housing)
        if housing.occupancy_type == "own" and housing.linked_debt_account_id:
            debt = (
                db.query(DebtAccount)
                .filter(DebtAccount.id == housing.linked_debt_account_id)
                .first()
            )
            if debt:
                result["mortgage"] = self._serialize_debt(debt)
        return result

    # ── Daily housing cost ────────────────────────────────────────────────────

    def apply_daily_housing_cost(
        self, player: Player, current_day: int, db: Session
    ) -> dict:
        """Apply daily housing cost once per in-game day (Step 8b revised flow)."""
        housing = self._get_active_housing(player, db)
        if not housing:
            raise ValueError("No active housing for this player.")
        if housing.last_cost_applied_day == current_day:
            raise ValueError(
                f"Daily housing cost already applied for day {current_day}."
            )

        defn = HOUSING_CATALOG.get(housing.housing_key)
        if not defn:
            raise ValueError(f"Housing definition not found for key: {housing.housing_key!r}")

        economy = self._get_economy(db)

        # ── Region pressure ───────────────────────────────────────────────────
        region_pressure = _balance.calculate_region_pressure_modifier(
            housing.region, housing.occupancy_type
        )
        housing.region_pressure_modifier = region_pressure

        daily_base = self._money(defn.daily_base_cost)
        debt_payment = self._money(0)
        interest_component = 0.0
        principal_component = 0.0
        property_tax_amount = self._money(0)
        maintenance_amount = self._money(0)
        maintenance_triggered = False
        maintenance_severity = "none"
        notes_parts: list[str] = [f"Daily {defn.occupancy_type} housing cost"]
        debt_obj: DebtAccount | None = None

        if housing.occupancy_type == "own":
            # ── Mortgage (penalty_rate_modifier applied via balance engine) ───
            if housing.linked_debt_account_id:
                debt_obj = (
                    db.query(DebtAccount)
                    .filter(DebtAccount.id == housing.linked_debt_account_id)
                    .first()
                )
            if debt_obj and float(debt_obj.principal_balance) > 0:
                components = _balance.calculate_daily_mortgage_components(debt_obj, economy)
                interest_component = components["interest_component"]
                principal_component = components["principal_component"]
                adjusted_payment = self._money(components["adjusted_minimum_payment"])

                current_principal = float(debt_obj.principal_balance)
                principal_reduction = min(principal_component, current_principal)
                debt_obj.principal_balance = self._money(current_principal - principal_reduction)
                debt_obj.cumulative_interest_paid = self._money(
                    float(debt_obj.cumulative_interest_paid or 0) + interest_component
                )
                debt_obj.cumulative_principal_paid = self._money(
                    float(debt_obj.cumulative_principal_paid or 0) + principal_reduction
                )
                debt_payment = adjusted_payment
                debt_obj.last_payment_day = current_day

            # ── Property tax daily accrual ────────────────────────────────────
            if housing.property_value and defn.property_tax_rate > 0:
                property_tax_amount = self._money(
                    float(housing.property_value) * defn.property_tax_rate / 365.0
                )

            # ── Maintenance (inflation-aware, downtown premium) ───────────────
            triggered, maint_cost, severity, maint_note = _balance.calculate_maintenance_pressure(
                housing, economy
            )
            if triggered:
                maintenance_amount = self._money(maint_cost)
                maintenance_triggered = True
                maintenance_severity = severity
                notes_parts.append(maint_note)

        total_cost = self._money(
            float(daily_base)
            + float(debt_payment)
            + float(property_tax_amount)
            + float(maintenance_amount)
        )

        # ── Affordability ─────────────────────────────────────────────────────
        cash_after_projected = float(player.cash) - float(total_cost)
        affordability_pressure = _balance.calculate_affordability_pressure(
            float(total_cost), cash_after_projected
        )
        housing.affordability_pressure = affordability_pressure

        # ── Payment (Option A: full pay or miss) ──────────────────────────────
        can_afford = float(player.cash) >= float(total_cost)
        credit_score_change = 0
        stability_change = 0
        delinquency_penalty = 0

        if can_afford:
            player.cash = self._money(float(player.cash) - float(total_cost))

            housing.cumulative_housing_paid = self._money(
                float(housing.cumulative_housing_paid or 0) + float(daily_base)
            )
            housing.cumulative_property_tax_paid = self._money(
                float(housing.cumulative_property_tax_paid or 0) + float(property_tax_amount)
            )
            housing.cumulative_maintenance_paid = self._money(
                float(housing.cumulative_maintenance_paid or 0) + float(maintenance_amount)
            )
            housing.cumulative_debt_paid = self._money(
                float(housing.cumulative_debt_paid or 0) + float(debt_payment)
            )

            housing.consecutive_missed_housing_days = 0
            if debt_obj:
                debt_obj.consecutive_missed_payments = 0
                if debt_obj.missed_payment_count > 0:
                    debt_obj.missed_payment_count = max(0, debt_obj.missed_payment_count - 1)
                debt_obj.delinquency_status = self._delinquency_from_count(
                    debt_obj.missed_payment_count
                )

            player.housing_stability = self._clamp_stability(player.housing_stability + 1)
            stability_change = 1
            # Credit improves slowly — once per 7 days max
            if current_day % 7 == 0:
                player.credit_score = self._clamp_credit(player.credit_score + 1)
                credit_score_change = 1

        else:
            shortfall = float(total_cost) - max(float(player.cash), 0.0)
            player.cash = self._money(0)

            housing.consecutive_missed_housing_days = int(
                housing.consecutive_missed_housing_days or 0
            ) + 1

            cs_change, stab_change, _ = _balance.apply_delinquency_progression(
                player, housing, debt_obj
            )
            credit_score_change = cs_change
            stability_change = stab_change
            delinquency_penalty = 1

            notes_parts.append(f"Missed payment — shortfall {shortfall:.2f}")
            if shortfall > 0.0:
                self._create_emergency_debt(player, shortfall, current_day, db)

        # ── Stress impact ─────────────────────────────────────────────────────
        stress_impact = _balance.calculate_housing_stress_impact(
            defn,
            affordability_pressure,
            missed_payment=not can_afford,
            maintenance_triggered=maintenance_triggered,
            maintenance_severity=maintenance_severity,
        )
        player.stress = self._clamp_stress(player.stress + stress_impact)

        housing.last_cost_applied_day = current_day
        housing.last_snapshot_day = current_day
        self._update_net_worth(player, db)

        db.add(HousingAction(
            player_id=player.id,
            housing_id=housing.id,
            action_type="pay_housing_cost",
            day=current_day,
            amount=total_cost,
            property_tax_amount=property_tax_amount,
            maintenance_amount=maintenance_amount,
            debt_payment_amount=debt_payment,
            stress_change=stress_impact,
            notes="; ".join(notes_parts),
        ))

        # ── Daily snapshot ────────────────────────────────────────────────────
        db.add(HousingDailySnapshot(
            player_id=player.id,
            housing_id=housing.id,
            day=current_day,
            region=housing.region,
            occupancy_type=housing.occupancy_type,
            daily_base_cost=daily_base,
            debt_payment_amount=debt_payment,
            property_tax_amount=property_tax_amount,
            maintenance_amount=maintenance_amount,
            total_housing_cost=total_cost,
            affordability_ratio=affordability_pressure,
            housing_stress_impact=stress_impact,
            delinquency_penalty=delinquency_penalty,
            credit_score_change=credit_score_change,
            housing_stability_change=stability_change,
            cash_after_housing=self._money(float(player.cash)),
            net_worth_after_housing=self._money(float(player.net_worth)),
        ))

        db.commit()
        db.refresh(player)

        return {
            "message": "Daily housing cost applied",
            "day": current_day,
            "region": housing.region,
            "occupancy_type": housing.occupancy_type,
            "daily_base_cost": float(daily_base),
            "debt_payment_amount": float(debt_payment),
            "property_tax_amount": float(property_tax_amount),
            "maintenance_amount": float(maintenance_amount),
            "total_housing_cost": float(total_cost),
            "affordability_pressure": affordability_pressure,
            "region_pressure_modifier": region_pressure,
            "housing_stress_impact": stress_impact,
            "credit_score_change": credit_score_change,
            "housing_stability_change": stability_change,
            "payment_successful": can_afford,
            "cash_remaining": float(player.cash),
            "updated_player": {
                "stress": player.stress,
                "credit_score": player.credit_score,
                "housing_stability": player.housing_stability,
                "net_worth": float(player.net_worth),
            },
        }

    # ── Debt management ───────────────────────────────────────────────────────

    def get_debt_accounts(self, player: Player, db: Session) -> list[dict]:
        """Return all debt accounts for the player."""
        debts = (
            db.query(DebtAccount)
            .filter(DebtAccount.player_id == player.id)
            .order_by(DebtAccount.originated_day.asc())
            .all()
        )
        return [self._serialize_debt(d) for d in debts]

    def pay_debt(
        self, player: Player, debt_account_id: str, amount: float, db: Session
    ) -> dict:
        """Make an extra manual payment on a debt account."""
        try:
            uid = _uuid_mod.UUID(debt_account_id)
        except ValueError:
            raise ValueError("Invalid debt_account_id format.")

        if amount <= 0:
            raise ValueError("Payment amount must be greater than zero.")

        debt = db.query(DebtAccount).filter(DebtAccount.id == uid).first()
        if not debt:
            raise ValueError("Debt account not found.")
        if debt.player_id != player.id:
            raise ValueError("You do not own that debt account.")
        if float(debt.principal_balance) <= 0:
            raise ValueError("This debt has already been paid off.")

        # Cannot pay more than owed
        payment = self._money(min(amount, float(debt.principal_balance)))
        if float(player.cash) < float(payment):
            raise ValueError(
                f"Insufficient cash. You have {float(player.cash):.2f}, "
                f"payment requires {float(payment):.2f}."
            )

        player.cash = self._money(float(player.cash) - float(payment))
        debt.principal_balance = self._money(
            max(0.0, float(debt.principal_balance) - float(payment))
        )
        current_day = self._get_current_day(db)
        debt.last_payment_day = current_day

        # Paying improves delinquency status incrementally
        if debt.missed_payment_count > 0:
            debt.missed_payment_count = max(0, debt.missed_payment_count - 1)
            debt.delinquency_status = self._delinquency_from_count(debt.missed_payment_count)

        self._update_net_worth(player, db)

        db.add(HousingAction(
            player_id=player.id,
            housing_id=None,
            action_type="make_debt_payment",
            day=current_day,
            amount=payment,
            debt_payment_amount=payment,
            notes=f"Manual payment on {debt.debt_type}",
        ))
        db.commit()
        db.refresh(player)
        db.refresh(debt)

        return {
            "message": "Debt payment applied",
            "debt_type": debt.debt_type,
            "amount_paid": float(payment),
            "principal_remaining": float(debt.principal_balance),
            "delinquency_status": debt.delinquency_status,
            "cash_remaining": float(player.cash),
            "net_worth": float(player.net_worth),
        }

    # ── History ───────────────────────────────────────────────────────────────

    def get_housing_history(self, player: Player, db: Session) -> list[dict]:
        """Return housing action history for the player, newest first (limit 100)."""
        rows = (
            db.query(HousingAction)
            .filter(HousingAction.player_id == player.id)
            .order_by(HousingAction.created_at.desc())
            .limit(100)
            .all()
        )
        return [
            {
                "id": str(r.id),
                "housing_id": str(r.housing_id) if r.housing_id else None,
                "action_type": r.action_type,
                "day": r.day,
                "amount": float(r.amount) if r.amount is not None else None,
                "property_tax_amount": float(r.property_tax_amount) if r.property_tax_amount is not None else None,
                "maintenance_amount": float(r.maintenance_amount) if r.maintenance_amount is not None else None,
                "debt_payment_amount": float(r.debt_payment_amount) if r.debt_payment_amount is not None else None,
                "stress_change": r.stress_change,
                "notes": r.notes,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]
