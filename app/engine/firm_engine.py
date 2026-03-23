"""app/engine/firm_engine.py — Step 14: Firm Layer economic engine.

All player gameplay (jobs, business, co-op deals, marketplace) continues to
work exactly as before.  The firm layer is purely additive — NPC firms run in
the background, generating supply-side economics that enrich the macro picture.

Key design choices:
  - NPC firms only in Step 14.  Player ownership is architecturally supported
    (owner_type="player", owner_player_id=<uuid>) but not yet game-exposed.
  - Player firm market-share impact is capped at PLAYER_FIRM_IMPACT_CAP (15%)
    per region/product to prevent single-player market dominance.
  - All P&L flows produce FirmLedgerEntry rows for full auditability.
  - run_daily_firm_cycle() is the single call point from the advance-day route.

Macro-to-firm mapping (requirement 12):
  basket input costs   → _compute_input_cost_pressure() → COGS ledger entries
  wage pressure        → macro.unemployment → adjusted wage_offer_xgp
  local demand changes → macro.consumer_confidence → demand_mult on revenue
  capacity utilization → FirmCapacity.utilization updated per production run
  distress changes     → roll_firm_distress() reads today's ledger net
"""

from __future__ import annotations

import json
import math
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.models.basket_price_history import BasketPriceHistory
from app.models.employment_contract import EmploymentContract
from app.models.firm import Firm
from app.models.firm_balance_snapshot import FirmBalanceSnapshot
from app.models.firm_capacity import FirmCapacity
from app.models.firm_ledger_entry import FirmLedgerEntry
from app.models.firm_policy import FirmPolicy
from app.models.game_state import GameState
from app.models.job_opening import JobOpening
from app.models.macro_state import MacroState
from app.models.market_share_state import MarketShareState

# ── Configuration ──────────────────────────────────────────────────────────────

# Maximum fraction of a regional product market that player-owned firms may supply.
PLAYER_FIRM_IMPACT_CAP: float = 0.15

# distress_level at-or-above which the firm status flips to "distressed".
DISTRESS_STATUS_THRESHOLD: int = 8

# ── NPC firm seed data ─────────────────────────────────────────────────────────

_NPC_FIRM_SEEDS: list[dict] = [
    {
        "name": "Downtown Fruit Market",
        "firm_type": "fruit_shop",
        "region": "downtown",
        "starting_cash": 3000.0,
    },
    {
        "name": "Downtown Food Truck Co.",
        "firm_type": "food_truck",
        "region": "downtown",
        "starting_cash": 4000.0,
    },
    {
        "name": "Suburban Fruit Market",
        "firm_type": "fruit_shop",
        "region": "suburban",
        "starting_cash": 2500.0,
    },
    {
        "name": "Suburban Food Truck Co.",
        "firm_type": "food_truck",
        "region": "suburban",
        "starting_cash": 3500.0,
    },
]

# Default capacity dimensions per firm_type.
_DEFAULT_CAPACITIES: dict[str, list[dict]] = {
    "fruit_shop": [
        {"capacity_type": "production", "base_capacity": 50.0},
        {"capacity_type": "storage",    "base_capacity": 200.0},
        {"capacity_type": "staffing",   "base_capacity": 3.0},
    ],
    "food_truck": [
        {"capacity_type": "production", "base_capacity": 40.0},
        {"capacity_type": "storage",    "base_capacity": 100.0},
        {"capacity_type": "staffing",   "base_capacity": 2.0},
        {"capacity_type": "delivery",   "base_capacity": 8.0},
    ],
}

# Default job types seeked by each firm_type (for opening generation).
_DEFAULT_JOB_SPECS: dict[str, list[dict]] = {
    "fruit_shop": [
        {"job_type": "retail_worker", "wage_offer_xgp": 80.0, "slots_total": 2},
    ],
    "food_truck": [
        {"job_type": "chef",            "wage_offer_xgp": 95.0, "slots_total": 1},
        {"job_type": "delivery_driver", "wage_offer_xgp": 75.0, "slots_total": 1},
    ],
}

# NPC workers seeded per firm_type (fictional employees whose payroll is simulated).
_DEFAULT_NPC_CONTRACTS: dict[str, list[dict]] = {
    "fruit_shop": [
        {"job_type": "retail_worker", "pay_type": "daily", "pay_rate_xgp": 80.0, "expected_hours": 8.0},
        {"job_type": "retail_worker", "pay_type": "daily", "pay_rate_xgp": 80.0, "expected_hours": 8.0},
    ],
    "food_truck": [
        {"job_type": "chef",            "pay_type": "daily", "pay_rate_xgp": 95.0, "expected_hours": 8.0},
        {"job_type": "delivery_driver", "pay_type": "daily", "pay_rate_xgp": 75.0, "expected_hours": 8.0},
    ],
}

# Base daily revenue and fixed overhead per firm_type (before macro adjustment).
_BASE_REVENUE: dict[str, Decimal] = {
    "fruit_shop": Decimal("320.00"),
    "food_truck":  Decimal("480.00"),
}
_BASE_OVERHEAD: dict[str, Decimal] = {
    "fruit_shop": Decimal("30.00"),
    "food_truck":  Decimal("55.00"),
}

# product_type produced by each firm_type (for market share tracking).
_FIRM_TYPE_TO_PRODUCT: dict[str, str] = {
    "fruit_shop": "produce",
    "food_truck":  "food",
}

# ── Helpers ────────────────────────────────────────────────────────────────────


def _money(val: Any) -> Decimal:
    return Decimal(str(val)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _current_day(db: Session) -> int:
    state = db.query(GameState).order_by(GameState.id.asc()).first()
    return int(state.current_day) if state else 1


def _get_latest_macro(db: Session) -> MacroState | None:
    return db.query(MacroState).order_by(MacroState.day_number.desc()).first()


def _get_active_firms(db: Session) -> list[Firm]:
    return db.query(Firm).filter(Firm.status.in_(["active", "distressed"])).all()


def _add_ledger_entry(
    db: Session,
    firm_id: int,
    day: int,
    category: str,
    direction: str,
    amount_xgp: Decimal,
    reference_type: str | None = None,
    reference_id: str | None = None,
    memo: str | None = None,
) -> FirmLedgerEntry:
    entry = FirmLedgerEntry(
        firm_id=firm_id,
        day=day,
        category=category,
        direction=direction,
        amount_xgp=amount_xgp,
        reference_type=reference_type,
        reference_id=reference_id,
        memo=memo,
    )
    db.add(entry)
    return entry


# ── Seeding ────────────────────────────────────────────────────────────────────


def get_or_seed_npc_firms(db: Session, created_day: int = 1) -> None:
    """Create the 4 NPC firm rows plus capacities, policies, and contracts.

    Idempotent: matches on (firm_type, region, owner_type='npc').
    Safe to call on every startup.
    """
    for spec in _NPC_FIRM_SEEDS:
        existing = (
            db.query(Firm)
            .filter(
                Firm.firm_type == spec["firm_type"],
                Firm.region == spec["region"],
                Firm.owner_type == "npc",
            )
            .first()
        )
        if existing is not None:
            continue

        firm = Firm(
            name=spec["name"],
            owner_type="npc",
            firm_type=spec["firm_type"],
            region=spec["region"],
            tier=1,
            status="active",
            reputation=Decimal("50.0"),
            cash_xgp=_money(spec["starting_cash"]),
            retained_earnings_xgp=Decimal("0.00"),
            distress_level=0,
            created_day=created_day,
        )
        db.add(firm)
        db.flush()  # acquire firm.id before adding related rows

        # ── Capacity dimensions ───────────────────────────────────────────────
        for cap_spec in _DEFAULT_CAPACITIES.get(spec["firm_type"], []):
            db.add(FirmCapacity(
                firm_id=firm.id,
                capacity_type=cap_spec["capacity_type"],
                base_capacity=_money(cap_spec["base_capacity"]),
                current_capacity=_money(cap_spec["base_capacity"]),
                utilization=Decimal("0.00"),
                maintenance_state="good",
                reliability=Decimal("1.00"),
            ))

        # ── Firm policy ───────────────────────────────────────────────────────
        db.add(FirmPolicy(
            firm_id=firm.id,
            hiring_aggressiveness=Decimal("0.50"),
            wage_strategy="market_rate",
            inventory_buffer_target=Decimal("0.20"),
            debt_tolerance=Decimal("0.30"),
            expansion_threshold=Decimal("5000.00"),
            is_active=True,
        ))

        # ── NPC employment contracts (fictional workers) ───────────────────────
        for contract_spec in _DEFAULT_NPC_CONTRACTS.get(spec["firm_type"], []):
            db.add(EmploymentContract(
                firm_id=firm.id,
                worker_type="npc",
                worker_player_id=None,
                job_type=contract_spec["job_type"],
                pay_type=contract_spec["pay_type"],
                pay_rate_xgp=_money(contract_spec["pay_rate_xgp"]),
                expected_hours=Decimal(str(contract_spec["expected_hours"])),
                active_from_day=created_day,
                active_to_day=None,
                status="active",
            ))

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise


# ── Job opening generation ─────────────────────────────────────────────────────


def generate_npc_job_openings(db: Session, current_day: int) -> None:
    """Refresh active NPC job openings for each firm.

    - One open JobOpening row per (firm_id, job_type) max.
    - If an open opening already exists, skip (avoid duplicates).
    - Wage is adjusted by macro unemployment pressure and firm wage_strategy.
    - Openings expire after 3 in-game days if not filled.
    - Stale (expired) openings are closed.
    """
    macro = _get_latest_macro(db)
    unemployment = float(macro.unemployment) if macro else 5.0

    # Low unemployment → higher wage pressure.  5.0 = baseline (1.0×).
    # Each point below 5% adds +3% wage; each point above subtracts.
    wage_pressure = max(0.80, 1.0 + (5.0 - unemployment) * 0.03)

    for firm in _get_active_firms(db):
        if firm.owner_type != "npc":
            continue

        policy = db.query(FirmPolicy).filter(FirmPolicy.firm_id == firm.id).first()
        wage_strategy = (policy.wage_strategy if policy and policy.is_active else "market_rate")
        strategy_mult = {"above_market": 1.20, "below_market": 0.80}.get(wage_strategy, 1.0)

        for job_spec in _DEFAULT_JOB_SPECS.get(firm.firm_type, []):
            already_open = (
                db.query(JobOpening)
                .filter(
                    JobOpening.firm_id == firm.id,
                    JobOpening.job_type == job_spec["job_type"],
                    JobOpening.status == "open",
                )
                .first()
            )
            if already_open is not None:
                continue

            adjusted_wage = _money(job_spec["wage_offer_xgp"] * wage_pressure * strategy_mult)
            db.add(JobOpening(
                firm_id=firm.id,
                region=firm.region,
                job_type=job_spec["job_type"],
                slots_total=job_spec["slots_total"],
                slots_filled=0,
                wage_offer_xgp=adjusted_wage,
                demand_multiplier=_money(wage_pressure * strategy_mult),
                source_type="npc_market",
                status="open",
                created_day=current_day,
                expires_day=current_day + 3,
            ))

    # Expire openings whose window has passed.
    stale = (
        db.query(JobOpening)
        .filter(
            JobOpening.status == "open",
            JobOpening.expires_day.isnot(None),
            JobOpening.expires_day < current_day,
        )
        .all()
    )
    for opening in stale:
        opening.status = "expired"

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise


# ── Macro-to-firm simulation ───────────────────────────────────────────────────


def _compute_input_cost_pressure(db: Session, firm_type: str) -> Decimal:
    """Return a cost multiplier derived from current basket price indices.

    fruit_shop — weighted toward produce (70%) and essentials (30%)
    food_truck  — essentials (40%) + produce (40%) + protein (20%)

    Falls back to 1.0 (baseline) if no price history exists yet.
    """
    latest: dict[str, Decimal] = {}
    for basket_id in ("essentials", "produce", "protein"):
        row = (
            db.query(BasketPriceHistory)
            .filter(BasketPriceHistory.basket_id == basket_id)
            .order_by(BasketPriceHistory.day_number.desc())
            .first()
        )
        if row:
            latest[basket_id] = Decimal(str(row.new_price_index))

    produce_idx     = latest.get("produce",     Decimal("1.0"))
    essentials_idx  = latest.get("essentials",  Decimal("1.0"))
    protein_idx     = latest.get("protein",     Decimal("1.0"))

    if firm_type == "fruit_shop":
        return _money(float(produce_idx) * 0.70 + float(essentials_idx) * 0.30)
    if firm_type == "food_truck":
        return _money(
            float(essentials_idx) * 0.40
            + float(produce_idx)    * 0.40
            + float(protein_idx)    * 0.20
        )
    return Decimal("1.0")


def apply_macro_to_firms(db: Session, current_day: int) -> None:
    """Map macro / supply-chain state to firm-level P&L ledger entries.

    For each active NPC firm this function:
      1. Computes daily revenue (demand driven by consumer_confidence).
      2. Computes daily NPC payroll from active EmploymentContracts.
      3. Computes COGS (basket price pressure × base cost).
      4. Computes fixed utility overhead.
      5. Writes FirmLedgerEntry rows for every flow category.
      6. Updates firm.cash_xgp and firm.retained_earnings_xgp.

    Mapping to requirement 12:
      basket input costs   → COGS entries weighted by basket price history
      wage pressure        → unemployment adjustment in generate_npc_job_openings
      local demand changes → consumer_confidence → demand_mult on daily revenue
      capacity utilization → staffing utilization updated here
      distress changes     → roll_firm_distress() reads this day's ledger net
    """
    macro = _get_latest_macro(db)
    confidence  = float(macro.consumer_confidence) if macro else 50.0

    # Demand multiplier: confidence 50→1.0, 80→1.15, 20→0.85 (clamped).
    demand_mult = max(0.70, min(1.40, 1.0 + (confidence - 50.0) / 200.0))

    for firm in _get_active_firms(db):
        if firm.owner_type != "npc":
            continue

        input_pressure = _compute_input_cost_pressure(db, firm.firm_type)
        base_revenue   = _BASE_REVENUE.get(firm.firm_type, Decimal("200.00"))
        base_overhead  = _BASE_OVERHEAD.get(firm.firm_type, Decimal("30.00"))

        # ── Revenue ──────────────────────────────────────────────────────────
        daily_revenue = _money(float(base_revenue) * demand_mult)
        _add_ledger_entry(
            db, firm.id, current_day, "revenue", "inflow", daily_revenue,
            memo=f"Daily {firm.firm_type} sales (confidence={confidence:.1f})",
        )

        # ── Payroll ──────────────────────────────────────────────────────────
        contracts = (
            db.query(EmploymentContract)
            .filter(
                EmploymentContract.firm_id == firm.id,
                EmploymentContract.status == "active",
                EmploymentContract.worker_type == "npc",
            )
            .all()
        )
        total_payroll = Decimal("0.00")
        for c in contracts:
            if c.pay_type == "daily":
                total_payroll += _money(float(c.pay_rate_xgp))
            elif c.pay_type == "hourly":
                total_payroll += _money(float(c.pay_rate_xgp) * float(c.expected_hours or 8))

        if total_payroll > Decimal("0.00"):
            _add_ledger_entry(
                db, firm.id, current_day, "payroll", "outflow", total_payroll,
                memo=f"{len(contracts)} NPC contract(s)",
            )

        # ── COGS (input cost, adjusted by basket price pressure) ──────────────
        base_cogs     = _money(float(base_revenue) * 0.35)
        adjusted_cogs = _money(float(base_cogs) * float(input_pressure))
        _add_ledger_entry(
            db, firm.id, current_day, "cogs", "outflow", adjusted_cogs,
            memo=f"Input cost index={float(input_pressure):.4f}",
        )

        # ── Fixed overhead ────────────────────────────────────────────────────
        _add_ledger_entry(
            db, firm.id, current_day, "utilities", "outflow", base_overhead,
            memo="Daily fixed overhead",
        )

        # ── Update firm financials ────────────────────────────────────────────
        net = daily_revenue - total_payroll - adjusted_cogs - base_overhead
        firm.cash_xgp             = _money(float(firm.cash_xgp)             + float(net))
        firm.retained_earnings_xgp = _money(float(firm.retained_earnings_xgp) + float(net))

        # ── Update staffing capacity utilization ──────────────────────────────
        staffing_cap = (
            db.query(FirmCapacity)
            .filter(
                FirmCapacity.firm_id == firm.id,
                FirmCapacity.capacity_type == "staffing",
            )
            .first()
        )
        if staffing_cap and float(staffing_cap.base_capacity) > 0:
            filled = float(len(contracts))
            staffing_cap.utilization = _money(
                min(1.0, filled / float(staffing_cap.base_capacity))
            )

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise


# ── Daily balance snapshots ────────────────────────────────────────────────────


def _estimate_avg_daily_overhead(db: Session, firm_id: int, current_day: int) -> float:
    """Average daily outflow over the previous 7 days from the ledger."""
    lookback = max(1, current_day - 7)
    entries = (
        db.query(FirmLedgerEntry)
        .filter(
            FirmLedgerEntry.firm_id == firm_id,
            FirmLedgerEntry.direction == "outflow",
            FirmLedgerEntry.day >= lookback,
            FirmLedgerEntry.day < current_day,
        )
        .all()
    )
    if not entries:
        return 0.0
    total = sum(float(e.amount_xgp) for e in entries)
    days  = max(1, current_day - lookback)
    return total / days


def produce_daily_firm_balance_snapshots(db: Session, current_day: int) -> None:
    """Create a FirmBalanceSnapshot for every active firm for current_day.

    Idempotent: skips if a snapshot for this (firm_id, day) already exists.
    """
    for firm in _get_active_firms(db):
        existing = (
            db.query(FirmBalanceSnapshot)
            .filter(
                FirmBalanceSnapshot.firm_id == firm.id,
                FirmBalanceSnapshot.day == current_day,
            )
            .first()
        )
        if existing is not None:
            continue

        cash         = float(firm.cash_xgp or 0)
        avg_overhead = _estimate_avg_daily_overhead(db, firm.id, current_day)
        runway       = None
        if avg_overhead > 0.01:
            runway = max(0, math.floor(cash / avg_overhead))

        db.add(FirmBalanceSnapshot(
            firm_id=firm.id,
            day=current_day,
            cash_xgp=_money(cash),
            inventory_value_xgp=Decimal("0.00"),
            receivables_xgp=Decimal("0.00"),
            payables_xgp=Decimal("0.00"),
            debt_outstanding_xgp=Decimal("0.00"),
            equity_estimate_xgp=_money(cash),   # MVP: equity ≈ cash
            runway_days=runway,
        ))

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise


# ── Distress rolling ───────────────────────────────────────────────────────────


def roll_firm_distress(db: Session, current_day: int) -> None:
    """Adjust distress_level for every active firm based on today's P&L.

    Rules:
      - Net outflow day (outflow > inflow): distress_level += 1 (max 10)
      - Net inflow day (profitable):        distress_level -= 1 (min 0)
      - distress_level >= DISTRESS_STATUS_THRESHOLD → status = "distressed"
      - status == "distressed" and distress_level < 4 → recover to "active"
    """
    for firm in _get_active_firms(db):
        inflow = sum(
            float(e.amount_xgp)
            for e in db.query(FirmLedgerEntry)
            .filter(
                FirmLedgerEntry.firm_id == firm.id,
                FirmLedgerEntry.day == current_day,
                FirmLedgerEntry.direction == "inflow",
            )
            .all()
        )
        outflow = sum(
            float(e.amount_xgp)
            for e in db.query(FirmLedgerEntry)
            .filter(
                FirmLedgerEntry.firm_id == firm.id,
                FirmLedgerEntry.day == current_day,
                FirmLedgerEntry.direction == "outflow",
            )
            .all()
        )

        if outflow > inflow:
            firm.distress_level = min(10, firm.distress_level + 1)
        else:
            firm.distress_level = max(0, firm.distress_level - 1)

        if firm.distress_level >= DISTRESS_STATUS_THRESHOLD:
            firm.status = "distressed"
        elif firm.status == "distressed" and firm.distress_level < 4:
            firm.status = "active"

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise


# ── Market share refresh ───────────────────────────────────────────────────────


def refresh_market_share_state(db: Session, current_day: int) -> None:
    """Compute and persist MarketShareState for each (region, product_type).

    Uses today's revenue ledger entries as a proxy for supply value.
    Player firm share is capped at PLAYER_FIRM_IMPACT_CAP of total supply.
    """
    all_firms = _get_active_firms(db)

    # Group firms by (region, product_type).
    groups: dict[tuple[str, str], list[Firm]] = {}
    for firm in all_firms:
        product_type = _FIRM_TYPE_TO_PRODUCT.get(firm.firm_type)
        if product_type is None:
            continue
        groups.setdefault((firm.region, product_type), []).append(firm)

    for (region, product_type), firms in groups.items():
        # Skip if a row for this (day, region, product_type) already exists.
        existing = (
            db.query(MarketShareState)
            .filter(
                MarketShareState.day == current_day,
                MarketShareState.region == region,
                MarketShareState.product_type == product_type,
            )
            .first()
        )
        if existing is not None:
            continue

        npc_total    = 0.0
        player_total = 0.0
        shares: list[dict] = []

        for firm in firms:
            daily_rev = sum(
                float(e.amount_xgp)
                for e in db.query(FirmLedgerEntry)
                .filter(
                    FirmLedgerEntry.firm_id == firm.id,
                    FirmLedgerEntry.day == current_day,
                    FirmLedgerEntry.direction == "inflow",
                    FirmLedgerEntry.category == "revenue",
                )
                .all()
            )
            if firm.owner_type in ("npc", "system"):
                npc_total += daily_rev
            else:
                player_total += daily_rev
            shares.append({
                "firm_id":     firm.id,
                "firm_type":   firm.firm_type,
                "supply_value": daily_rev,
            })

        total_supply = npc_total + player_total

        # Enforce the player impact cap.
        if total_supply > 0 and player_total / total_supply > PLAYER_FIRM_IMPACT_CAP:
            player_total = total_supply * PLAYER_FIRM_IMPACT_CAP

        # Annotate share percentages.
        for s in shares:
            s["share_pct"] = (
                round(s["supply_value"] / total_supply * 100, 2) if total_supply > 0 else 0.0
            )

        db.add(MarketShareState(
            day=current_day,
            region=region,
            product_type=product_type,
            total_npc_supply=Decimal(str(round(npc_total, 4))),
            total_player_supply=Decimal(str(round(player_total, 4))),
            average_price_index=Decimal("1.0"),   # future: derive from basket history
            unmet_demand=Decimal("0.0"),           # future: compare against region demand signal
            firm_shares_json=json.dumps(shares),
        ))

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise


# ── Daily cycle entry point ────────────────────────────────────────────────────


def run_daily_firm_cycle(db: Session, current_day: int) -> None:
    """Run all firm-layer daily operations in dependency order.

    Called once per advance-day from the daily API route.
    All player gameplay continues to work whether or not any player-owned
    firms exist — this cycle is purely additive.

    Order:
      1. apply_macro_to_firms           — revenue + cost entries; update cash
      2. produce_daily_firm_balance_snapshots — snapshot end-of-day position
      3. roll_firm_distress             — escalate or recover distress
      4. generate_npc_job_openings      — refresh open job postings
      5. refresh_market_share_state     — regional product supply picture
    """
    apply_macro_to_firms(db, current_day)
    produce_daily_firm_balance_snapshots(db, current_day)
    roll_firm_distress(db, current_day)
    generate_npc_job_openings(db, current_day)
    refresh_market_share_state(db, current_day)
