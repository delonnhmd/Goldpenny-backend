"""Business Engine — Step 7 (legacy) + Step 10 (small business system).

Step 7 (legacy):  class BusinessEngine — full-featured business system,
                  multi-tier upgrades, inventory management, old models.
Step 10 (new):    module-level functions — simple deterministic small-business
                  loop, BusinessType / PlayerBusiness / BusinessOperation.

Design rules (Step 10)
----------------------
- Business converts daily labor + basket inputs into capital.
  Profit depends on macro demand — not a guaranteed income source.
- Inputs connect directly to the basket economy: produce, essentials,
  and protein costs move with oil, inflation, and supply-chain stress.
- One operation per business per day (idempotency guard).
- One business per player (enforced by UniqueConstraint on player_businesses).
- Revenue is deterministic: confidence and unemployment drive the modifier.
- All XGP movement creates an XGPTransaction ledger row.
- Every operation creates a ContributionEvent row for the reward engine.
- Businesses create a genuine risk/reward decision: starting a business
  costs XGP and time; operating it costs basket inputs and hours; profit
  is not guaranteed when macro conditions are unfavourable.
"""

from __future__ import annotations

import json as _json
import random
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.models.business import Business
from app.models.business_action import BusinessAction
from app.models.business_daily_snapshot import BusinessDailySnapshot
from app.models.business_definition import (
    BASKET_BASE_PRICES,
    BUSINESS_CATALOG,
    REGION_DEMAND_MOD,
    REGION_PRICE_MOD,
    TIER_DEMAND_BOOST,
    BusinessDefinition,
)
from app.models.business_inventory import BusinessInventory
from app.models.business_operation import BusinessOperation
from app.models.business_type import DEFAULT_BUSINESS_TYPES, BusinessType
from app.models.contribution_event import ContributionEvent
from app.models.economy import EconomyState
from app.models.game_state import GameState
from app.models.goods_basket import GoodsBasket
from app.models.macro_state import MacroState
from app.models.player import Player
from app.models.player_business import PlayerBusiness
from app.engine import business_balance_engine as _balance

# ── Constants (shared) ────────────────────────────────────────────────────────

_MAX_ACTIVE_BUSINESSES = 1
_MIN_HEALTH_TO_OPERATE = 20
_MAX_FATIGUE_TO_OPERATE = 95.0

_D = Decimal

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# STEP 10 — Small Business System (module-level functions)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_STEP10_REVENUE_MIN_MULT: float = 0.75   # floor: macro can reduce revenue by 25%
_STEP10_REVENUE_MAX_MULT: float = 1.25   # cap:   macro can boost revenue by 25%


def get_or_seed_business_types(db: Session) -> list[BusinessType]:
    """Ensure both default BusinessType rows exist.  Idempotent.

    Inserts missing business types and returns the full list of active ones.
    Called once at application startup.
    """
    for spec in DEFAULT_BUSINESS_TYPES:
        existing = (
            db.query(BusinessType)
            .filter(BusinessType.business_id == spec["business_id"])
            .first()
        )
        if existing is None:
            db.add(BusinessType(**spec))
    db.commit()
    return db.query(BusinessType).filter(BusinessType.is_active.is_(True)).all()


def _get_basket_unit_price(db: Session, basket_id: str) -> float:
    """Return the live unit price for *basket_id* (base_price × price_index / 100)."""
    basket = db.query(GoodsBasket).filter(GoodsBasket.id == basket_id).first()
    if basket is None:
        return 0.0
    return float(basket.base_price) * (float(basket.price_index) / 100.0)


def calculate_business_input_cost(db: Session, business_type: BusinessType) -> float:
    """Return the total XGP cost of basket inputs for one business operation.

    Input costs are live — they move with the basket price index, which is
    affected by oil, inflation, and supply chain conditions.  This connects
    business operating costs directly to the macro economy.

    Cost breakdown:
      produce_cost    = produce_units    × live produce price per unit
      essentials_cost = essentials_units × live essentials price per unit
      protein_cost    = protein_units    × live protein price per unit
    """
    produce_price    = _get_basket_unit_price(db, "produce")
    essentials_price = _get_basket_unit_price(db, "essentials")
    protein_price    = _get_basket_unit_price(db, "protein")

    produce_cost    = business_type.input_produce_units    * produce_price
    essentials_cost = business_type.input_essentials_units * essentials_price
    protein_cost    = business_type.input_protein_units    * protein_price

    return round(produce_cost + essentials_cost + protein_cost, 4)


def calculate_business_revenue(
    business_type: BusinessType, macro: MacroState
) -> float:
    """Return macro-adjusted revenue for one business operation.

    Revenue formula:
      revenue = base_revenue × (1 + confidence_factor) × (1 - unemployment_factor)

    Where:
      confidence_factor   = (consumer_confidence - 50.0) / 200.0
        + confident consumers spend more; range roughly [-0.25, +0.25]
      unemployment_factor = (unemployment - 5.0) / 100.0
        + high unemployment reduces demand; range roughly [-0.05, +0.15]

    Result is clamped to [base_revenue × 0.75, base_revenue × 1.25] so a
    single bad macro day can never destroy or double the business in one go.

    Businesses respond to macro demand — this is intentional and creates
    strategic timing decisions for players (wait for better conditions vs.
    operate every day for steady cash flow).
    """
    base = float(business_type.base_revenue)

    confidence_factor   = (float(macro.consumer_confidence) - 50.0) / 200.0
    unemployment_factor = (float(macro.unemployment) - 5.0) / 100.0

    raw_multiplier = (1 + confidence_factor) * (1 - unemployment_factor)
    clamped = max(_STEP10_REVENUE_MIN_MULT, min(_STEP10_REVENUE_MAX_MULT, raw_multiplier))

    return round(base * clamped, 4)


def validate_business_operation(
    db: Session,
    player: Player,
    player_business: PlayerBusiness,
    business_type: BusinessType,
) -> tuple[bool, str | None]:
    """Check all preconditions before allowing an operation.

    Returns (True, None) when valid; (False, reason) otherwise.

    Anti-exploit guards (Step 10 + Step 11):
      1. Player must own an active business.
      2. Must have enough hours_available.
      3. Must have enough cash to cover input costs + fixed overhead.
         (Step 11: overhead is now always included so the guard reflects the
         true minimum cash required, not just basket input cost.)

    Note: the Step 10 one-per-day idempotency guard has been intentionally
    removed in Step 11.  Multiple daily runs are now allowed but are
    progressively weakened by the saturation penalty system.
    """
    if not player_business.is_active:
        return False, "Your business is not active."

    hours_needed = business_type.hours_required
    if player.hours_available < hours_needed:
        return (
            False,
            f"Not enough hours. Need {hours_needed}h, have {player.hours_available}h.",
        )

    input_cost    = calculate_business_input_cost(db, business_type)
    fixed_overhead = _balance.calculate_fixed_overhead(business_type)
    min_cash_needed = input_cost + fixed_overhead
    bal = float(player.cash)
    if bal < min_cash_needed:
        return (
            False,
            (
                f"Not enough cash. Need {min_cash_needed:.2f} XGP "
                f"(inputs {input_cost:.2f} + overhead {fixed_overhead:.2f}), "
                f"have {bal:.2f} XGP."
            ),
        )

    return True, None


def _s10_get_current_day(db: Session) -> int:
    state = db.query(GameState).order_by(GameState.id.asc()).first()
    return int(state.current_day) if state else 0


def process_business_operation(
    db: Session,
    player: Player,
    player_business: PlayerBusiness,
    business_type: BusinessType,
) -> dict[str, Any]:
    """Execute one day's business operation atomically with full Step 11 balancing.

    Steps:
      1. Validate preconditions (hours, cash covering inputs + overhead).
      2. Get current game day and macro state.
      3. Reset saturation counter if a new game day has started.
      4. Compute base input cost and base revenue.
      5. Run all five Step 11 balancing functions:
           - calculate_fixed_overhead
           - calculate_demand_multiplier
           - calculate_saturation_penalty_multiplier
           - calculate_macro_margin_modifier
           - calculate_final_margin_multiplier
      6. adjusted_revenue = base_revenue × final_margin_multiplier
         profit            = adjusted_revenue − input_cost − fixed_overhead
         (profit may be negative — this is intentional and economically meaningful)
      7. Update player: cash += profit, hours -= required, stress += change.
      8. Update player_business: times_operated_today, last_operated_day,
         lifetime_business_runs.
      9. Write BusinessOperation, XGPTransaction, ContributionEvent rows.
     10. Commit and return expanded summary dict.

    Raises ValueError with a user-facing message if validation fails.
    """
    from app.engine.macro_engine import get_or_create_macro_state_for_day
    from app.models.xgp_transaction import XGPTransaction

    # ── Pre-flight validation ──────────────────────────────────────────────────
    ok, err = validate_business_operation(db, player, player_business, business_type)
    if not ok:
        raise ValueError(err)

    # ── Gather context ─────────────────────────────────────────────────────────
    day_number = _s10_get_current_day(db)
    macro = get_or_create_macro_state_for_day(db, day_number)

    # ── Reset daily saturation counter when a new game day is detected ─────────
    # If the player's last run was on a different day, today's counter starts at 0.
    # We read it before incrementing so the CURRENT run uses its true saturation level.
    if player_business.last_operated_day != day_number:
        player_business.times_operated_today = 0
    times_operated_today = int(player_business.times_operated_today or 0)

    # ── Base economics ─────────────────────────────────────────────────────────
    balance_before   = round(float(player.cash), 4)
    input_cost       = calculate_business_input_cost(db, business_type)
    base_revenue_xgp = float(business_type.base_revenue)

    # ── Step 11 balancing ──────────────────────────────────────────────────────
    fixed_overhead = _balance.calculate_fixed_overhead(business_type)

    demand_mult = _balance.calculate_demand_multiplier(
        business_type,
        consumer_confidence=float(macro.consumer_confidence),
        unemployment=float(macro.unemployment),
    )
    saturation_mult = _balance.calculate_saturation_penalty_multiplier(
        business_type,
        times_operated_today=times_operated_today,
    )
    macro_modifier = _balance.calculate_macro_margin_modifier(
        business_type,
        oil_index=float(macro.oil_index),
        inflation=float(macro.inflation),
        input_cost_xgp=input_cost,
        base_revenue_xgp=base_revenue_xgp,
    )
    final_mult = _balance.calculate_final_margin_multiplier(
        demand_mult, saturation_mult, macro_modifier
    )

    # ── Compute final revenue and profit ───────────────────────────────────────
    # Revenue is adjusted by the full margin multiplier (demand × saturation + macro).
    # Overhead is then subtracted along with input costs.
    # Negative profit is intentional: a bad run is an economic loss, not a no-op.
    adjusted_revenue = round(base_revenue_xgp * final_mult, 4)
    profit           = round(adjusted_revenue - input_cost - fixed_overhead, 4)
    balance_after    = round(balance_before + profit, 4)

    stress_change  = business_type.stress_change
    hours_required = business_type.hours_required

    # ── Mutate player ──────────────────────────────────────────────────────────
    player.cash            = Decimal(str(balance_after))
    player.hours_available = max(0, player.hours_available - hours_required)
    player.stress          = min(100, (player.stress or 0) + stress_change)

    # ── Update business state ──────────────────────────────────────────────────
    player_business.times_operated_today  = times_operated_today + 1
    player_business.last_operated_day     = day_number
    player_business.lifetime_business_runs = int(
        player_business.lifetime_business_runs or 0
    ) + 1

    # ── BusinessOperation audit row ────────────────────────────────────────────
    op = BusinessOperation(
        player_id=player.id,
        business_id=business_type.business_id,
        day_number=day_number,
        hours_used=hours_required,
        produce_units=business_type.input_produce_units,
        essentials_units=business_type.input_essentials_units,
        protein_units=business_type.input_protein_units,
        input_cost_xgp=Decimal(str(input_cost)),
        revenue_xgp=Decimal(str(adjusted_revenue)),
        profit_xgp=Decimal(str(profit)),
        stress_change=stress_change,
        balance_before=Decimal(str(balance_before)),
        balance_after=Decimal(str(balance_after)),
        # Step 11 balancing audit fields
        fixed_overhead_xgp=Decimal(str(fixed_overhead)),
        demand_multiplier=demand_mult,
        saturation_penalty_multiplier=saturation_mult,
        macro_margin_modifier=macro_modifier,
        final_margin_multiplier=final_mult,
    )
    db.add(op)
    db.flush()

    # ── XGPTransaction ledger ──────────────────────────────────────────────────
    # One net transaction per run records the full economic outcome.
    # Profit > 0 = net inflow; profit < 0 = net outflow (loss day).
    if profit >= 0:
        xgp_direction = "in"
        xgp_type      = "business_revenue"
    else:
        xgp_direction = "out"
        xgp_type      = "business_loss"

    xgp_tx = XGPTransaction(
        player_id=player.id,
        transaction_type=xgp_type,
        direction=xgp_direction,
        amount=round(abs(profit), 4),
        balance_before=balance_before,
        balance_after=balance_after,
        reference_type="business_operation",
        reference_id=str(op.id),
        description=(
            f"Business op \u2014 {business_type.display_name} "
            f"@ day {day_number}: adj_revenue {adjusted_revenue:.2f}, "
            f"inputs {input_cost:.2f}, overhead {fixed_overhead:.2f}, "
            f"profit {profit:.2f} "
            f"[demand={demand_mult}, sat={saturation_mult}, macro={macro_modifier}]"
        ),
    )
    db.add(xgp_tx)

    # ── ContributionEvent ──────────────────────────────────────────────────────
    contribution = ContributionEvent(
        player_id=player.id,
        event_type="business_operation",
        xgp_value=round(adjusted_revenue, 4),
        event_units=float(hours_required),
        metadata_json=_json.dumps({
            "business_id":                   business_type.business_id,
            "display_name":                  business_type.display_name,
            "day_number":                    day_number,
            "input_cost_xgp":               input_cost,
            "fixed_overhead_xgp":           fixed_overhead,
            "revenue_xgp":                  adjusted_revenue,
            "profit_xgp":                   profit,
            "demand_multiplier":            demand_mult,
            "saturation_penalty_multiplier": saturation_mult,
            "macro_margin_modifier":        macro_modifier,
            "final_margin_multiplier":      final_mult,
            "times_operated_today":         times_operated_today + 1,
            "produce_units":                business_type.input_produce_units,
            "essentials_units":             business_type.input_essentials_units,
            "protein_units":                business_type.input_protein_units,
            "hours_used":                   hours_required,
            "stress_change":                stress_change,
        }),
    )
    db.add(contribution)

    db.commit()

    return {
        "business_id":                   business_type.business_id,
        "display_name":                  business_type.display_name,
        "day_number":                    day_number,
        "hours_used":                    hours_required,
        "input_cost_xgp":               input_cost,
        "fixed_overhead_xgp":           fixed_overhead,
        "revenue_xgp":                  adjusted_revenue,
        "profit_xgp":                   profit,
        "demand_multiplier":            demand_mult,
        "saturation_penalty_multiplier": saturation_mult,
        "macro_margin_modifier":        macro_modifier,
        "final_margin_multiplier":      final_mult,
        "stress_change":                stress_change,
        "balance_before":               balance_before,
        "balance_after":                balance_after,
        "times_operated_today":         times_operated_today + 1,
        "lifetime_business_runs":       int(player_business.lifetime_business_runs),
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# STEP 7 LEGACY — BusinessEngine (class-based, old models)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class BusinessEngine:
    """Processes all player business actions for Gold Penny."""

    # ── Internal helpers ─────────────────────────────────────────────────────

    def _money(self, val: Any) -> Decimal:
        return Decimal(str(val)).quantize(_D("0.01"), rounding=ROUND_HALF_UP)

    def _get_current_day(self, db: Session) -> int:
        state = db.query(GameState).order_by(GameState.id.asc()).first()
        return int(state.current_day) if state else 1

    def _get_economy(self, db: Session) -> EconomyState | None:
        return db.query(EconomyState).order_by(EconomyState.day.desc()).first()

    def _get_definition(self, business_type: str) -> BusinessDefinition:
        defn = BUSINESS_CATALOG.get(business_type)
        if defn is None:
            valid = list(BUSINESS_CATALOG)
            raise ValueError(
                f"Unknown business type '{business_type}'. Valid types: {valid}"
            )
        return defn

    def _active_count(self, player_id: Any, db: Session) -> int:
        return (
            db.query(Business)
            .filter(Business.player_id == player_id, Business.status == "active")
            .count()
        )

    def _get_business_owned(self, business_id: str, player_id: Any, db: Session) -> Business:
        business = db.query(Business).filter(Business.id == business_id).first()
        if business is None:
            raise ValueError("Business not found.")
        if str(business.player_id) != str(player_id):
            raise ValueError("This business does not belong to you.")
        return business

    def _player_region(self, player: Player) -> str:
        region = getattr(player, "region", None) or "suburban"
        return region

    # ── Basket pricing ───────────────────────────────────────────────────────

    def get_basket_price(self, basket_name: str, player: Player, db: Session) -> Decimal:
        """Current per-unit price for a basket, adjusted for economy and region."""
        if basket_name not in BASKET_BASE_PRICES:
            valid = list(BASKET_BASE_PRICES)
            raise ValueError(f"Unknown basket '{basket_name}'. Valid: {valid}")

        base = _D(str(BASKET_BASE_PRICES[basket_name]))
        economy = self._get_economy(db)

        inflation_mod = _D("1.0")
        supply_mod = _D("1.0")
        if economy:
            # Inflation above 5 % adds cost pressure
            if economy.inflation_rate > 5.0:
                inflation_mod = _D(str(1.0 + (economy.inflation_rate - 5.0) * 0.01))
            # Supply chain below 90 adds cost pressure
            if economy.supply_chain_index < 90.0:
                supply_mod = _D(str(1.0 + (90.0 - economy.supply_chain_index) * 0.003))

        region_mod = _D(str(REGION_PRICE_MOD.get(self._player_region(player), 1.0)))
        return self._money(base * inflation_mod * supply_mod * region_mod)

    # ── START BUSINESS ───────────────────────────────────────────────────────

    def start_business(
        self,
        player: Player,
        business_type: str,
        business_name: str,
        db: Session,
    ) -> dict[str, Any]:
        defn = self._get_definition(business_type)

        if self._active_count(player.id, db) >= _MAX_ACTIVE_BUSINESSES:
            raise ValueError(
                "You already have an active business. "
                "Close it first before starting a new one."
            )

        startup_cost = self._money(defn.startup_cost)
        if self._money(player.cash) < startup_cost:
            raise ValueError(
                f"Insufficient cash. Need ${startup_cost}, "
                f"have ${self._money(player.cash)}."
            )

        # Deduct startup cost
        player.cash = self._money(player.cash) - startup_cost

        tier = defn.upgrade_path[0]
        business = Business(
            player_id=player.id,
            business_type=business_type,
            business_name=business_name.strip(),
            tier=tier,
            status="active",
            startup_cost_paid=startup_cost,
            current_cash_invested=startup_cost,
            cumulative_revenue=_D("0"),
            cumulative_expense=startup_cost,
            cumulative_profit=-startup_cost,
        )
        db.add(business)
        db.flush()  # get business.id before creating action

        current_day = self._get_current_day(db)
        action = BusinessAction(
            business_id=business.id,
            player_id=player.id,
            day=current_day,
            action_type="start_business",
            overhead_cost=startup_cost,
            net_profit=-startup_cost,
            notes=(
                f"'{business_name.strip()}' started as {defn.display_name} "
                f"at tier '{tier}'."
            ),
        )
        db.add(action)
        db.commit()
        db.refresh(business)

        return {
            "message": "Business created",
            "business_id": str(business.id),
            "business_type": business_type,
            "business_name": business.business_name,
            "tier": tier,
            "startup_cost": float(startup_cost),
            "cash_remaining": float(self._money(player.cash)),
        }

    # ── BUY BUSINESS INVENTORY ───────────────────────────────────────────────

    def buy_business_inventory(
        self,
        player: Player,
        business_id: str,
        basket_name: str,
        quantity: int,
        db: Session,
    ) -> dict[str, Any]:
        if quantity <= 0:
            raise ValueError("Quantity must be a positive integer.")

        business = self._get_business_owned(business_id, player.id, db)
        if business.status != "active":
            raise ValueError(f"Cannot buy inventory for a '{business.status}' business.")

        defn = self._get_definition(business.business_type)
        if basket_name not in defn.required_input_baskets:
            raise ValueError(
                f"'{basket_name}' is not a valid input for {defn.display_name}. "
                f"Allowed: {defn.required_input_baskets}"
            )

        unit_price = self.get_basket_price(basket_name, player, db)
        total_cost = self._money(unit_price * quantity)

        if self._money(player.cash) < total_cost:
            raise ValueError(
                f"Insufficient cash. Need ${total_cost} for {quantity} × {basket_name}, "
                f"have ${self._money(player.cash)}."
            )

        # Deduct cash
        player.cash = self._money(player.cash) - total_cost

        # Upsert inventory row
        current_day = self._get_current_day(db)
        inv = (
            db.query(BusinessInventory)
            .filter(
                BusinessInventory.business_id == business.id,
                BusinessInventory.basket_name == basket_name,
            )
            .first()
        )
        if inv is None:
            inv = BusinessInventory(
                business_id=business.id,
                basket_name=basket_name,
                quantity=quantity,
                freshness=1.0,
                created_day=current_day,
            )
            db.add(inv)
        else:
            inv.quantity += quantity
            # Fresh restock restores freshness partially
            inv.freshness = min(1.0, inv.freshness + 0.2)

        # Log action (no cumulative update — COGS recognised at consumption)
        action = BusinessAction(
            business_id=business.id,
            player_id=player.id,
            day=current_day,
            action_type="buy_inventory",
            input_cost=total_cost,
            net_profit=-total_cost,
            notes=f"Bought {quantity} × {basket_name} @ ${unit_price} each.",
        )
        db.add(action)
        db.commit()
        db.refresh(inv)

        return {
            "message": f"Purchased {quantity} × {basket_name}.",
            "basket_name": basket_name,
            "quantity_bought": quantity,
            "unit_price": float(unit_price),
            "total_cost": float(total_cost),
            "cash_remaining": float(self._money(player.cash)),
            "inventory_quantity_now": inv.quantity,
        }

    # ── OPERATE BUSINESS ─────────────────────────────────────────────────────

    def operate_business(
        self,
        player: Player,
        business_id: str,
        db: Session,
    ) -> dict[str, Any]:
        business = self._get_business_owned(business_id, player.id, db)
        if business.status != "active":
            raise ValueError(f"Cannot operate a '{business.status}' business.")

        defn = self._get_definition(business.business_type)
        current_day = self._get_current_day(db)

        # ── Daily operation limit ─────────────────────────────────────────────
        if business.last_operated_day == current_day:
            raise ValueError(
                "This business has already been operated today. Try again tomorrow."
            )

        # ── Player vitals guards ──────────────────────────────────────────────
        if int(player.health) < _MIN_HEALTH_TO_OPERATE:
            raise ValueError(
                f"Health too low ({player.health}). "
                f"You need at least {_MIN_HEALTH_TO_OPERATE} health to operate."
            )
        if float(player.fatigue) > _MAX_FATIGUE_TO_OPERATE:
            raise ValueError(
                f"Fatigue too high ({player.fatigue:.1f}). Rest before operating."
            )
        if int(player.hours_available) < defn.time_cost_hours:
            raise ValueError(
                f"Not enough hours available. Need {defn.time_cost_hours}h, "
                f"have {player.hours_available}h."
            )

        # ── Check and load required inventory ────────────────────────────────
        inventory: dict[str, BusinessInventory] = {}
        for basket_name in defn.required_input_baskets:
            needed = defn.input_consumption.get(basket_name, 1)
            inv = (
                db.query(BusinessInventory)
                .filter(
                    BusinessInventory.business_id == business.id,
                    BusinessInventory.basket_name == basket_name,
                )
                .first()
            )
            have = inv.quantity if inv else 0
            if have < needed:
                raise ValueError(
                    f"Insufficient inventory: need {needed} × {basket_name}, "
                    f"have {have}. Buy more before operating."
                )
            inventory[basket_name] = inv

        # ── Economy snapshot ─────────────────────────────────────────────────
        economy = self._get_economy(db)
        oil_index = float(economy.oil_index) if economy else 100.0
        consumer_confidence = float(economy.consumer_confidence) if economy else 100.0
        inflation_rate = float(economy.inflation_rate) if economy else 2.5

        # ── Input cost basis (cost of goods sold — COGS) ─────────────────────
        input_cost = _D("0")
        consumed: dict[str, int] = {}
        for basket_name in defn.required_input_baskets:
            units = defn.input_consumption[basket_name]
            unit_price = self.get_basket_price(basket_name, player, db)
            input_cost += self._money(unit_price * units)
            consumed[basket_name] = units

        # Consume inventory (deduct units)
        for basket_name, inv in inventory.items():
            inv.quantity -= consumed[basket_name]

        # ── Overhead cost ─────────────────────────────────────────────────────
        overhead_cost = self._money(defn.daily_overhead)

        # ── Fuel cost (food_truck scales with oil index) ──────────────────────
        fuel_cost = _D("0")
        if defn.fuel_sensitivity == "high":
            raw_fuel = 5.0 + (oil_index - 100.0) * 0.08
            fuel_cost = self._money(max(raw_fuel, 2.0))

        # ── Spoilage ──────────────────────────────────────────────────────────
        spoiled_units = 0
        spoilage_cost = _D("0")
        if defn.spoilage_risk == "high" and random.random() < 0.35:
            spoiled_units = 1
            primary_basket = defn.required_input_baskets[0]
            spoilage_cost = self.get_basket_price(primary_basket, player, db)
            spoil_inv = inventory.get(primary_basket)
            if spoil_inv and spoil_inv.quantity >= 1:
                spoil_inv.quantity -= 1
        elif defn.spoilage_risk == "medium" and random.random() < 0.15:
            spoiled_units = 1
            primary_basket = defn.required_input_baskets[0]
            spoilage_cost = self.get_basket_price(primary_basket, player, db)
            spoil_inv = inventory.get(primary_basket)
            if spoil_inv and spoil_inv.quantity >= 1:
                spoil_inv.quantity -= 1

        # ── Operating efficiency (player condition) ───────────────────────────
        efficiency = (
            1.0
            - 0.003 * float(player.stress)
            - 0.002 * float(player.fatigue)
            - 0.003 * (100 - int(player.health))
        )
        efficiency = max(0.50, min(1.10, efficiency))

        # ── Demand factor ─────────────────────────────────────────────────────
        region = self._player_region(player)
        region_mod = REGION_DEMAND_MOD.get(region, 1.0)

        # Consumer confidence centred on 100
        confidence_mod = max(0.70, min(1.30, consumer_confidence / 100.0))

        # High inflation compresses discretionary demand
        inflation_mod = 1.0
        if inflation_rate > 7.0:
            inflation_mod = max(0.85, 1.0 - (inflation_rate - 7.0) * 0.02)

        # Food truck: high oil suppresses demand further
        oil_demand_mod = 1.0
        if defn.fuel_sensitivity == "high" and oil_index > 120.0:
            oil_demand_mod = max(0.85, 1.0 - (oil_index - 120.0) * 0.002)

        tier_mod = TIER_DEMAND_BOOST.get(business.tier, 1.0)

        demand_factor = (
            defn.base_customer_demand
            * region_mod
            * confidence_mod
            * inflation_mod
            * oil_demand_mod
            * efficiency
            * tier_mod
        )
        demand_factor = max(0.40, min(2.0, demand_factor))

        # ── Revenue and profit ────────────────────────────────────────────────
        gross_revenue = self._money(
            input_cost
            * _D(str(defn.revenue_multiplier))
            * _D(str(round(demand_factor, 6)))
        )
        total_expenses = input_cost + overhead_cost + fuel_cost + spoilage_cost
        net_profit = self._money(gross_revenue - total_expenses)

        # Cash: player receives revenue, pays overhead / fuel / spoilage
        # (input_cost already left player's wallet at inventory purchase time)
        player.cash = self._money(player.cash) + gross_revenue - overhead_cost - fuel_cost - spoilage_cost

        # ── Player condition ──────────────────────────────────────────────────
        player.hours_available = max(0, int(player.hours_available) - defn.time_cost_hours)
        player.stress = max(0, min(100, int(player.stress) + defn.stress_change_per_op))
        player.health = max(0, min(100, int(player.health) - defn.health_change_per_op))
        player.fatigue = max(0.0, min(100.0, float(player.fatigue) + defn.fatigue_change_per_op))

        # ── Update business cumulative stats ─────────────────────────────────
        business.cumulative_revenue = self._money(business.cumulative_revenue) + gross_revenue
        business.cumulative_expense = self._money(business.cumulative_expense) + total_expenses
        business.cumulative_profit = self._money(business.cumulative_profit) + net_profit
        business.times_operated = int(business.times_operated) + 1
        business.last_operated_day = current_day

        # ── Log action ────────────────────────────────────────────────────────
        action = BusinessAction(
            business_id=business.id,
            player_id=player.id,
            day=current_day,
            action_type="operate",
            input_cost=input_cost,
            overhead_cost=overhead_cost,
            fuel_cost=fuel_cost,
            revenue_generated=gross_revenue,
            units_sold=sum(consumed.values()),
            spoiled_units=spoiled_units,
            stress_change=defn.stress_change_per_op,
            health_change=defn.health_change_per_op,
            time_spent=defn.time_cost_hours,
            net_profit=net_profit,
            notes=(
                f"demand={demand_factor:.3f} efficiency={efficiency:.2f} "
                f"consumed={consumed} region={region} tier={business.tier}"
            ),
        )
        db.add(action)
        db.commit()

        return {
            "message": "Business operated successfully",
            "business_id": str(business.id),
            "business_type": business.business_type,
            "tier": business.tier,
            "demand_factor": round(demand_factor, 4),
            "operating_efficiency": round(efficiency, 4),
            "revenue_generated": float(gross_revenue),
            "input_cost": float(input_cost),
            "overhead_cost": float(overhead_cost),
            "fuel_cost": float(fuel_cost),
            "spoilage_cost": float(spoilage_cost),
            "spoiled_units": spoiled_units,
            "net_profit": float(net_profit),
            "time_spent": defn.time_cost_hours,
            "stress_change": defn.stress_change_per_op,
            "health_change": defn.health_change_per_op,
            "updated_player": {
                "cash": float(self._money(player.cash)),
                "hours_available": int(player.hours_available),
                "health": int(player.health),
                "stress": int(player.stress),
                "fatigue": float(player.fatigue),
            },
        }

    # ── UPGRADE BUSINESS ─────────────────────────────────────────────────────

    def upgrade_business(
        self,
        player: Player,
        business_id: str,
        db: Session,
    ) -> dict[str, Any]:
        business = self._get_business_owned(business_id, player.id, db)
        if business.status != "active":
            raise ValueError(f"Cannot upgrade a '{business.status}' business.")

        defn = self._get_definition(business.business_type)
        upgrade_path = defn.upgrade_path
        current_tier = business.tier

        try:
            current_idx = upgrade_path.index(current_tier)
        except ValueError:
            raise ValueError(f"Unknown tier '{current_tier}' for this business type.")

        if current_idx >= len(upgrade_path) - 1:
            raise ValueError(
                f"'{current_tier}' is the maximum tier. No further upgrades available."
            )

        next_tier = upgrade_path[current_idx + 1]

        # MVP: block the final food_truck tier
        if next_tier == "restaurant_future":
            raise ValueError(
                "The 'restaurant_future' upgrade is not yet available. "
                "Stay tuned for a future update."
            )

        upgrade_cost = self._money(defn.upgrade_costs.get(current_tier, 0.0))
        if upgrade_cost <= 0:
            raise ValueError(
                f"No upgrade available from tier '{current_tier}'."
            )

        if self._money(player.cash) < upgrade_cost:
            raise ValueError(
                f"Insufficient cash. Upgrading to '{next_tier}' costs ${upgrade_cost}, "
                f"have ${self._money(player.cash)}."
            )

        player.cash = self._money(player.cash) - upgrade_cost
        business.tier = next_tier
        business.current_cash_invested = self._money(business.current_cash_invested) + upgrade_cost
        business.cumulative_expense = self._money(business.cumulative_expense) + upgrade_cost
        business.cumulative_profit = self._money(business.cumulative_profit) - upgrade_cost

        current_day = self._get_current_day(db)
        action = BusinessAction(
            business_id=business.id,
            player_id=player.id,
            day=current_day,
            action_type="upgrade",
            overhead_cost=upgrade_cost,
            net_profit=-upgrade_cost,
            notes=f"Upgraded from '{current_tier}' to '{next_tier}'.",
        )
        db.add(action)
        db.commit()

        return {
            "message": f"Business upgraded to '{next_tier}'.",
            "business_id": str(business.id),
            "previous_tier": current_tier,
            "new_tier": next_tier,
            "upgrade_cost": float(upgrade_cost),
            "cash_remaining": float(self._money(player.cash)),
        }

    # ── CLOSE BUSINESS ───────────────────────────────────────────────────────

    def close_business(
        self,
        player: Player,
        business_id: str,
        db: Session,
    ) -> dict[str, Any]:
        business = self._get_business_owned(business_id, player.id, db)
        if business.status == "closed":
            raise ValueError("Business is already closed.")

        business.status = "closed"
        current_day = self._get_current_day(db)
        action = BusinessAction(
            business_id=business.id,
            player_id=player.id,
            day=current_day,
            action_type="close",
            notes="Business closed by player.",
        )
        db.add(action)
        db.commit()

        return {
            "message": "Business closed.",
            "business_id": str(business.id),
            "final_cumulative_profit": float(self._money(business.cumulative_profit)),
        }

    # ── READ HELPERS ─────────────────────────────────────────────────────────

    def get_player_businesses(self, player_id: Any, db: Session) -> list[dict[str, Any]]:
        businesses = (
            db.query(Business)
            .filter(Business.player_id == player_id)
            .order_by(Business.created_at.desc())
            .all()
        )
        return [self._serialize_business(b) for b in businesses]

    def _serialize_business(self, b: Business) -> dict[str, Any]:
        return {
            "business_id": str(b.id),
            "business_type": b.business_type,
            "business_name": b.business_name,
            "tier": b.tier,
            "status": b.status,
            "startup_cost_paid": float(b.startup_cost_paid),
            "current_cash_invested": float(b.current_cash_invested),
            "cumulative_revenue": float(b.cumulative_revenue),
            "cumulative_expense": float(b.cumulative_expense),
            "cumulative_profit": float(b.cumulative_profit),
            "times_operated": b.times_operated,
            "last_operated_day": b.last_operated_day,
            "consecutive_profitable_days": int(getattr(b, "consecutive_profitable_days", 0) or 0),
            "consecutive_loss_days": int(getattr(b, "consecutive_loss_days", 0) or 0),
            "demand_reputation": round(float(getattr(b, "demand_reputation", 1.0) or 1.0), 4),
            "current_margin_modifier": round(float(getattr(b, "current_margin_modifier", 1.0) or 1.0), 4),
            "lifetime_units_sold": int(getattr(b, "lifetime_units_sold", 0) or 0),
            "lifetime_spoiled_units": int(getattr(b, "lifetime_spoiled_units", 0) or 0),
            "created_at": b.created_at.isoformat() if b.created_at else None,
        }

    def get_business_inventory(
        self, business_id: str, player_id: Any, db: Session
    ) -> list[dict[str, Any]]:
        business = self._get_business_owned(business_id, player_id, db)
        rows = (
            db.query(BusinessInventory)
            .filter(BusinessInventory.business_id == business.id)
            .all()
        )
        return [
            {
                "basket_name": r.basket_name,
                "quantity": r.quantity,
                "freshness": r.freshness,
                "created_day": r.created_day,
            }
            for r in rows
        ]
