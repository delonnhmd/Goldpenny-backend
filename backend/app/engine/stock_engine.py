"""Stock Engine — Step 6 (legacy) + Step 9 (sector stock system).

Step 6 (legacy):  class StockEngine — random-noise price updates, old models.
Step 9 (new):     module-level functions — deterministic macro-driven prices,
                  SectorStock / StockPriceHistory / PlayerStockHolding / StockTrade.

Design rules (Step 9)
---------------------
- Price changes are fully deterministic: macro variables drive every move.
- Each sensitivity coefficient controls how strongly one macro variable
  affects the stock.  See calculate_stock_daily_change_percent().
- Daily change is clamped to ±6% (SectorStocks are smoother than old system).
- Price floor is 1.00 XGP.
- 0.3% transaction fee on all trades (both buy and sell).
- Every cash mutation creates an XGPTransaction ledger row.
- Every trade creates a ContributionEvent row for the reward engine.
- apply_daily_stock_price_update() is idempotent — safe to call twice.
"""

from __future__ import annotations

import json as _json
import random
from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.contribution_event import ContributionEvent
from app.models.game_state import GameState
from app.models.macro_state import MacroState
from app.models.player import Player
from app.models.player_stock_holding import PlayerStockHolding
from app.models.portfolio import Portfolio
from app.models.sector_index import SectorIndex
from app.models.sector_stock import DEFAULT_SECTOR_STOCKS, SectorStock
from app.models.stock import Stock
from app.models.stock_price_history import StockPriceHistory
from app.models.stock_trade import StockTrade
from app.models.trade import Trade

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# STEP 9 — Sector Stock System (module-level functions)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_STEP9_MIN_PRICE: Decimal = Decimal("1.00")
_STEP9_MAX_DAILY_MOVE: float = 0.06   # ±6 % daily cap
_STEP9_FEE_RATE: float = 0.003        # 0.3 % transaction fee


def get_or_seed_default_sector_stocks(db: Session) -> list[SectorStock]:
    """Ensure all 10 default SectorStock rows exist.  Idempotent.

    Inserts missing stocks and returns the full list of active stocks.
    This is called once at application startup.
    """
    for spec in DEFAULT_SECTOR_STOCKS:
        existing = (
            db.query(SectorStock)
            .filter(SectorStock.stock_id == spec["stock_id"])
            .first()
        )
        if existing is None:
            db.add(SectorStock(**spec))
    db.commit()
    return db.query(SectorStock).filter(SectorStock.is_active.is_(True)).all()


def calculate_stock_daily_change_percent(
    stock: SectorStock,
    macro: MacroState,
) -> float:
    """Return the deterministic daily price-change fraction for *stock*.

    Each macro variable is normalised against its neutral baseline so that
    "normal" conditions produce zero drift.  The sensitivity coefficients
    (stored on SectorStock) control the magnitude and direction.

    Baselines:
        consumer_confidence  = 50.0   (out of 100)
        inflation            =  2.0 % (target)
        unemployment         =  5.0 %
        oil_index            = 100.0  (index baseline)
        interest_rate        =  4.0 %

    Result is clamped to [-0.06, +0.06] (i.e. ±6%) to prevent runaway prices.
    """
    confidence_component = (
        (float(macro.consumer_confidence) - 50.0) / 100.0
    ) * float(stock.confidence_sensitivity)

    inflation_component = (
        (float(macro.inflation) - 2.0) / 100.0
    ) * float(stock.inflation_sensitivity)

    oil_component = (
        (float(macro.oil_index) - 100.0) / 100.0
    ) * float(stock.oil_sensitivity)

    unemployment_component = (
        (float(macro.unemployment) - 5.0) / 100.0
    ) * float(stock.unemployment_sensitivity)

    interest_rate_component = (
        (float(macro.interest_rate) - 4.0) / 100.0
    ) * float(stock.interest_rate_sensitivity)

    raw_change = (
        confidence_component
        + inflation_component
        + oil_component
        + unemployment_component
        + interest_rate_component
    )

    return max(-_STEP9_MAX_DAILY_MOVE, min(_STEP9_MAX_DAILY_MOVE, raw_change))


def apply_daily_stock_price_update(
    db: Session, day_number: int
) -> list[StockPriceHistory]:
    """Update SectorStock.current_price for every active stock for *day_number*.

    Idempotent: if a StockPriceHistory row already exists for a (stock, day)
    pair, that stock is skipped.  This makes the endpoint safe to call twice.

    Returns the list of newly written StockPriceHistory rows.
    """
    from app.engine.macro_engine import get_or_create_macro_state_for_day  # lazy import to avoid circular

    macro = get_or_create_macro_state_for_day(db, day_number)
    stocks = (
        db.query(SectorStock).filter(SectorStock.is_active.is_(True)).all()
    )

    written: list[StockPriceHistory] = []
    for stock in stocks:
        # Idempotency guard
        already_exists = (
            db.query(StockPriceHistory)
            .filter(
                StockPriceHistory.stock_id == stock.stock_id,
                StockPriceHistory.day_number == day_number,
            )
            .first()
        )
        if already_exists is not None:
            continue

        old_price = float(stock.current_price)
        change_pct = calculate_stock_daily_change_percent(stock, macro)
        raw_new = Decimal(str(old_price)) * (Decimal("1") + Decimal(str(change_pct)))
        new_price = max(
            _STEP9_MIN_PRICE,
            raw_new.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP),
        )

        stock.current_price = new_price

        history = StockPriceHistory(
            stock_id=stock.stock_id,
            day_number=day_number,
            old_price=Decimal(str(old_price)).quantize(
                Decimal("0.0001"), rounding=ROUND_HALF_UP
            ),
            new_price=new_price,
            change_percent=Decimal(str(round(change_pct, 6))).quantize(
                Decimal("0.000001"), rounding=ROUND_HALF_UP
            ),
            inflation_used=macro.inflation,
            interest_rate_used=macro.interest_rate,
            unemployment_used=macro.unemployment,
            oil_index_used=macro.oil_index,
            consumer_confidence_used=macro.consumer_confidence,
        )
        db.add(history)
        written.append(history)

    db.commit()
    return written


def calculate_trade_fee(gross_amount: float, fee_rate: float = _STEP9_FEE_RATE) -> float:
    """Return the 0.3% transaction fee, rounded to 2 decimal places."""
    return round(gross_amount * fee_rate, 2)


def validate_stock_trade(
    trade_type: str,
    shares: int,
    balance: float,
    stock_price: float,
    shares_owned: int = 0,
) -> tuple[bool, str | None]:
    """Validate a proposed stock trade.

    Returns (True, None) when valid; (False, error_message) otherwise.
    """
    if trade_type not in ("buy", "sell"):
        return False, "trade_type must be 'buy' or 'sell'."
    if not isinstance(shares, int) or shares <= 0:
        return False, "shares must be a positive integer."

    if trade_type == "buy":
        gross = stock_price * shares
        fee = calculate_trade_fee(gross)
        total_cost = gross + fee
        if balance < total_cost:
            return (
                False,
                f"Insufficient balance. Need {total_cost:.2f} XGP (incl. {fee:.2f} fee), "
                f"have {balance:.2f} XGP.",
            )

    elif trade_type == "sell":
        if shares_owned < shares:
            return (
                False,
                f"Insufficient holdings. Tried to sell {shares}, own {shares_owned}.",
            )

    return True, None


def process_stock_trade(
    db: Session,
    player: Player,
    stock_id: str,
    trade_type: str,
    shares: int,
) -> dict[str, Any]:
    """Execute a BUY or SELL for the given player.

    Atomically:
     1. Validates the trade.
     2. Mutates player.cash and PlayerStockHolding.
     3. Writes StockTrade, XGPTransaction, and ContributionEvent rows.
     4. Commits.

    Raises ValueError with a user-facing message on any validation failure.
    Returns a summary dict on success.
    """
    from app.models.xgp_transaction import XGPTransaction  # avoid circular imports

    stock = (
        db.query(SectorStock)
        .filter(SectorStock.stock_id == stock_id, SectorStock.is_active.is_(True))
        .first()
    )
    if stock is None:
        raise ValueError(f"Stock '{stock_id}' not found or is not active.")

    state = db.query(GameState).order_by(GameState.id.asc()).first()
    day_number: int = int(state.current_day) if state else 0

    stock_price = float(stock.current_price)
    balance_before = round(float(player.cash), 4)

    # Load or initialise holding
    holding = (
        db.query(PlayerStockHolding)
        .filter(
            PlayerStockHolding.player_id == player.id,
            PlayerStockHolding.stock_id == stock_id,
        )
        .first()
    )
    shares_owned = holding.shares_owned if holding else 0

    # Validate
    ok, err = validate_stock_trade(
        trade_type, shares, balance_before, stock_price, shares_owned
    )
    if not ok:
        raise ValueError(err)

    gross_amount = round(stock_price * shares, 4)
    fee = calculate_trade_fee(gross_amount)

    if trade_type == "buy":
        net_amount = round(gross_amount + fee, 4)
        player.cash = round(balance_before - net_amount, 4)
        xgp_direction = "out"
        xgp_type = "stock_buy"

        # Update holding (weighted average cost basis)
        if holding is None:
            holding = PlayerStockHolding(
                player_id=player.id,
                stock_id=stock_id,
                shares_owned=0,
                average_cost_basis=Decimal("0"),
                total_cost_basis=Decimal("0"),
            )
            db.add(holding)
            db.flush()

        old_shares = holding.shares_owned
        old_avg = float(holding.average_cost_basis)
        new_total_shares = old_shares + shares
        new_avg = round(
            (old_avg * old_shares + stock_price * shares) / new_total_shares, 4
        )
        holding.shares_owned = new_total_shares
        holding.average_cost_basis = Decimal(str(new_avg))
        holding.total_cost_basis = Decimal(str(round(new_avg * new_total_shares, 4)))

    else:  # sell
        net_amount = round(gross_amount - fee, 4)
        player.cash = round(balance_before + net_amount, 4)
        xgp_direction = "in"
        xgp_type = "stock_sell"

        # Reduce holding
        holding.shares_owned -= shares
        if holding.shares_owned == 0:
            holding.average_cost_basis = Decimal("0")
            holding.total_cost_basis = Decimal("0")
        else:
            remaining_cost = float(holding.total_cost_basis) - (
                float(holding.average_cost_basis) * shares
            )
            holding.total_cost_basis = Decimal(str(round(remaining_cost, 4)))

    balance_after = round(float(player.cash), 4)

    # StockTrade audit row
    trade_row = StockTrade(
        player_id=player.id,
        stock_id=stock_id,
        day_number=day_number,
        trade_type=trade_type,
        shares=shares,
        price_per_share=Decimal(str(stock_price)),
        gross_amount=Decimal(str(gross_amount)),
        transaction_fee=Decimal(str(fee)),
        net_amount=Decimal(str(net_amount)),
        balance_before=Decimal(str(balance_before)),
        balance_after=Decimal(str(balance_after)),
    )
    db.add(trade_row)
    db.flush()

    # XGPTransaction ledger
    from app.models.xgp_transaction import XGPTransaction
    xgp_tx = XGPTransaction(
        player_id=player.id,
        transaction_type=xgp_type,
        direction=xgp_direction,
        amount=round(net_amount, 4),
        balance_before=balance_before,
        balance_after=balance_after,
        reference_type="stock_trade",
        reference_id=str(trade_row.id),
        description=f"Stock {trade_type} — {stock.display_name} x{shares} @ {stock_price:.4f}",
    )
    db.add(xgp_tx)

    # ContributionEvent
    contribution = ContributionEvent(
        player_id=player.id,
        event_type="stock_trade",
        xgp_value=round(gross_amount, 4),
        event_units=float(shares),
        metadata_json=_json.dumps({
            "stock_id": stock_id,
            "display_name": stock.display_name,
            "trade_type": trade_type,
            "shares": shares,
            "price_per_share": stock_price,
            "gross_amount": gross_amount,
            "transaction_fee": fee,
            "day_number": day_number,
        }),
    )
    db.add(contribution)

    db.commit()

    return {
        "stock_id": stock_id,
        "display_name": stock.display_name,
        "trade_type": trade_type,
        "shares": shares,
        "price_per_share": stock_price,
        "gross_amount": gross_amount,
        "transaction_fee": fee,
        "net_amount": net_amount,
        "balance_before": balance_before,
        "balance_after": balance_after,
        "day_number": day_number,
    }


def build_sector_portfolio_summary(db: Session, player: Player) -> dict[str, Any]:
    """Return a full portfolio summary for the player's SectorStock holdings.

    Only includes holdings where shares_owned > 0.
    Fetches live prices from SectorStock.
    """
    holdings = (
        db.query(PlayerStockHolding)
        .filter(
            PlayerStockHolding.player_id == player.id,
            PlayerStockHolding.shares_owned > 0,
        )
        .all()
    )

    if not holdings:
        return {
            "holdings": [],
            "total_cost_basis": 0.0,
            "total_market_value": 0.0,
            "total_unrealized_pl": 0.0,
        }

    stock_ids = [h.stock_id for h in holdings]
    stocks_by_id: dict[str, SectorStock] = {
        s.stock_id: s
        for s in db.query(SectorStock).filter(SectorStock.stock_id.in_(stock_ids)).all()
    }

    items: list[dict[str, Any]] = []
    total_cost = 0.0
    total_market = 0.0

    for h in holdings:
        stock = stocks_by_id.get(h.stock_id)
        current_price = float(stock.current_price) if stock else 0.0
        avg_cost = float(h.average_cost_basis)
        market_value = round(current_price * h.shares_owned, 4)
        cost_value = round(avg_cost * h.shares_owned, 4)
        unrealized_pl = round(market_value - cost_value, 4)
        unrealized_pl_pct = (
            round((unrealized_pl / cost_value) * 100, 4) if cost_value > 0 else 0.0
        )

        items.append({
            "stock_id": h.stock_id,
            "display_name": stock.display_name if stock else h.stock_id,
            "sector_type": stock.sector_type if stock else None,
            "shares_owned": h.shares_owned,
            "average_cost_basis": avg_cost,
            "current_price": current_price,
            "market_value": market_value,
            "unrealized_pl": unrealized_pl,
            "unrealized_pl_percent": unrealized_pl_pct,
        })

        total_cost += cost_value
        total_market += market_value

    total_pl = round(total_market - total_cost, 4)

    return {
        "holdings": items,
        "total_cost_basis": round(total_cost, 4),
        "total_market_value": round(total_market, 4),
        "total_unrealized_pl": total_pl,
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# STEP 6 LEGACY — StockEngine (random-based, old models)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# ── Initial catalog ───────────────────────────────────────────────────────────

_INITIAL_STOCKS: list[dict[str, Any]] = [
    {
        "symbol": "AUR",
        "name": "AUR Energy Corp",
        "company_name": "AUR Energy Corp",
        "sector": "energy",
        "base_price": Decimal("35.00"),
        "volatility": 0.70,
        "growth_bias": 0.02,
    },
    {
        "symbol": "NEX",
        "name": "NEX Tech Labs",
        "company_name": "NEX Tech Labs",
        "sector": "tech",
        "base_price": Decimal("120.00"),
        "volatility": 0.80,
        "growth_bias": 0.05,
    },
    {
        "symbol": "BNK",
        "name": "BNK Capital Group",
        "company_name": "BNK Capital Group",
        "sector": "bank",
        "base_price": Decimal("50.00"),
        "volatility": 0.45,
        "growth_bias": 0.01,
    },
    {
        "symbol": "HLT",
        "name": "HLT Healthcare Systems",
        "company_name": "HLT Healthcare Systems",
        "sector": "health",
        "base_price": Decimal("80.00"),
        "volatility": 0.30,
        "growth_bias": 0.02,
    },
    {
        "symbol": "AGR",
        "name": "AGR Foods",
        "company_name": "AGR Foods",
        "sector": "consumer",
        "base_price": Decimal("20.00"),
        "volatility": 0.35,
        "growth_bias": 0.01,
    },
    {
        "symbol": "TRN",
        "name": "TRN Logistics",
        "company_name": "TRN Logistics",
        "sector": "transport",
        "base_price": Decimal("35.00"),
        "volatility": 0.55,
        "growth_bias": 0.00,
    },
    {
        "symbol": "RLT",
        "name": "RLT Realty Holdings",
        "company_name": "RLT Realty Holdings",
        "sector": "real_estate",
        "base_price": Decimal("65.00"),
        "volatility": 0.40,
        "growth_bias": 0.01,
    },
    {
        "symbol": "AUTO",
        "name": "AUTO Motors",
        "company_name": "AUTO Motors",
        "sector": "auto",
        "base_price": Decimal("50.00"),
        "volatility": 0.60,
        "growth_bias": 0.00,
    },
    {
        "symbol": "DEF",
        "name": "DEF Systems",
        "company_name": "DEF Systems",
        "sector": "defense",
        "base_price": Decimal("80.00"),
        "volatility": 0.25,
        "growth_bias": 0.02,
    },
    {
        "symbol": "RET",
        "name": "RET Market Holdings",
        "company_name": "RET Market Holdings",
        "sector": "retail",
        "base_price": Decimal("35.00"),
        "volatility": 0.50,
        "growth_bias": -0.01,
    },
]

# Hard caps
_MAX_DAILY_MOVE_PCT = 12.0   # ±12% maximum daily price change
_MIN_PRICE = Decimal("1.00")


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _d(value: float | str) -> Decimal:
    return Decimal(str(value))


# ── Engine ────────────────────────────────────────────────────────────────────

class StockEngine:
    def __init__(self, rng: random.Random | None = None) -> None:
        self.rng = rng or random.Random()

    # ── Seeding ───────────────────────────────────────────────────────────────

    def seed_stocks(self, db: Session) -> list[str]:
        """Insert initial stock catalog if not already present.

        Returns list of symbols that were newly seeded.
        """
        seeded: list[str] = []
        for spec in _INITIAL_STOCKS:
            existing = db.query(Stock).filter(Stock.symbol == spec["symbol"]).first()
            if existing is not None:
                continue
            stock = Stock(
                symbol=spec["symbol"],
                name=spec["name"],
                company_name=spec["company_name"],
                sector=spec["sector"],
                base_price=spec["base_price"],
                current_price=spec["base_price"],
                last_price=spec["base_price"],
                volatility=spec["volatility"],
                growth_bias=spec["growth_bias"],
            )
            db.add(stock)
            seeded.append(spec["symbol"])
        if seeded:
            db.commit()
        return seeded

    # ── Daily price update ────────────────────────────────────────────────────

    def update_daily_stock_prices(self, day: int, db: Session) -> list[dict[str, Any]]:
        """Update every stock's current_price based on sector index for *day*.

        Sector move is the primary driver; company noise is layered on top.
        Returns a list of update summaries.
        """
        # Load sector index changes for this day.
        sector_rows = db.query(SectorIndex).filter(SectorIndex.day == day).all()
        sector_changes: dict[str, float] = {
            r.sector_name: r.daily_change_percent for r in sector_rows
        }

        stocks = db.query(Stock).all()
        if not stocks:
            return []

        results: list[dict[str, Any]] = []
        for stock in stocks:
            old_price = float(stock.current_price)
            sector_change = sector_changes.get(stock.sector, 0.0)
            company_noise = self.rng.uniform(-stock.volatility, stock.volatility)
            growth_effect = float(stock.growth_bias)

            raw_pct = sector_change + company_noise + growth_effect
            clamped_pct = _clamp(raw_pct, -_MAX_DAILY_MOVE_PCT, _MAX_DAILY_MOVE_PCT)
            new_price = max(
                _MIN_PRICE,
                _d(old_price * (1 + clamped_pct / 100.0)).quantize(
                    Decimal("0.0001"), rounding=ROUND_HALF_UP
                ),
            )

            stock.last_price = stock.current_price
            stock.current_price = new_price

            results.append(
                {
                    "symbol": stock.symbol,
                    "sector": stock.sector,
                    "old_price": round(old_price, 4),
                    "new_price": float(new_price),
                    "daily_change_percent": round(clamped_pct, 4),
                    "sector_change_percent": round(sector_change, 4),
                }
            )

        db.commit()
        return results

    # ── Trade execution ───────────────────────────────────────────────────────

    def buy_stock(
        self,
        player: Player,
        symbol: str,
        shares: int,
        db: Session,
    ) -> dict[str, Any]:
        """Execute a BUY order.

        Raises ValueError with a user-friendly message on any validation failure.
        """
        if shares <= 0:
            raise ValueError("Shares must be a positive integer.")

        stock = db.query(Stock).filter(Stock.symbol == symbol.upper()).first()
        if stock is None:
            raise ValueError(f"Stock symbol '{symbol}' not found.")

        price = Decimal(str(stock.current_price))
        total_cost = (price * shares).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        player_cash = Decimal(str(player.cash))
        if player_cash < total_cost:
            raise ValueError(
                f"Insufficient cash. Need ${total_cost}, have ${player_cash:.2f}."
            )

        # Deduct cash.
        player.cash = (player_cash - total_cost).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        # Update portfolio.
        holding = (
            db.query(Portfolio)
            .filter(Portfolio.player_id == player.id, Portfolio.stock_symbol == symbol.upper())
            .first()
        )
        if holding is None:
            holding = Portfolio(
                player_id=player.id,
                stock_symbol=symbol.upper(),
                shares=0,
                average_price=Decimal("0"),
            )
            db.add(holding)
            db.flush()

        # Compute new volume-weighted average price.
        old_shares = holding.shares
        old_avg = Decimal(str(holding.average_price))
        new_shares = old_shares + shares
        new_avg = (
            (old_avg * old_shares + price * shares) / new_shares
        ).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)

        holding.shares = new_shares
        holding.average_price = new_avg

        # Record trade.
        current_day = self._get_current_day(db)
        trade = Trade(
            player_id=player.id,
            stock_symbol=symbol.upper(),
            trade_type="BUY",
            shares=shares,
            price_per_share=price,
            total_value=total_cost,
            day=current_day,
        )
        db.add(trade)
        db.commit()

        return {
            "message": "Purchase successful",
            "symbol": symbol.upper(),
            "shares": shares,
            "price": float(price),
            "total_cost": float(total_cost),
            "cash_remaining": float(player.cash),
        }

    def sell_stock(
        self,
        player: Player,
        symbol: str,
        shares: int,
        db: Session,
    ) -> dict[str, Any]:
        """Execute a SELL order.

        Raises ValueError with a user-friendly message on any validation failure.
        """
        if shares <= 0:
            raise ValueError("Shares must be a positive integer.")

        stock = db.query(Stock).filter(Stock.symbol == symbol.upper()).first()
        if stock is None:
            raise ValueError(f"Stock symbol '{symbol}' not found.")

        holding = (
            db.query(Portfolio)
            .filter(Portfolio.player_id == player.id, Portfolio.stock_symbol == symbol.upper())
            .first()
        )
        if holding is None or holding.shares < shares:
            owned = holding.shares if holding else 0
            raise ValueError(
                f"Insufficient holdings. Tried to sell {shares}, own {owned}."
            )

        price = Decimal(str(stock.current_price))
        proceeds = (price * shares).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        # Credit cash.
        player.cash = (
            Decimal(str(player.cash)) + proceeds
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        # Update portfolio.
        holding.shares -= shares
        if holding.shares == 0:
            # Reset average price when fully exited.
            holding.average_price = Decimal("0")

        # Record trade.
        current_day = self._get_current_day(db)
        trade = Trade(
            player_id=player.id,
            stock_symbol=symbol.upper(),
            trade_type="SELL",
            shares=shares,
            price_per_share=price,
            total_value=proceeds,
            day=current_day,
        )
        db.add(trade)
        db.commit()

        return {
            "message": "Sale successful",
            "symbol": symbol.upper(),
            "shares": shares,
            "price": float(price),
            "total_proceeds": float(proceeds),
            "cash_remaining": float(player.cash),
        }

    # ── Portfolio queries ─────────────────────────────────────────────────────

    def get_portfolio(self, player_id: UUID, db: Session) -> list[dict[str, Any]]:
        """Return all non-zero holdings with live P&L calculations."""
        holdings = (
            db.query(Portfolio)
            .filter(Portfolio.player_id == player_id, Portfolio.shares > 0)
            .all()
        )
        if not holdings:
            return []

        symbols = [h.stock_symbol for h in holdings]
        stocks_by_symbol: dict[str, Stock] = {
            s.symbol: s
            for s in db.query(Stock).filter(Stock.symbol.in_(symbols)).all()
        }

        result: list[dict[str, Any]] = []
        for h in holdings:
            stock = stocks_by_symbol.get(h.stock_symbol)
            current_price = float(stock.current_price) if stock else 0.0
            market_value = round(current_price * h.shares, 2)
            avg = float(h.average_price)
            cost_basis = round(avg * h.shares, 2)
            profit_loss = round(market_value - cost_basis, 2)
            result.append(
                {
                    "symbol": h.stock_symbol,
                    "shares": h.shares,
                    "average_price": avg,
                    "current_price": current_price,
                    "market_value": market_value,
                    "cost_basis": cost_basis,
                    "profit_loss": profit_loss,
                    "profit_loss_pct": (
                        round((profit_loss / cost_basis) * 100, 2) if cost_basis > 0 else 0.0
                    ),
                    "sector": stock.sector if stock else None,
                }
            )
        return result

    def get_portfolio_summary(self, player_id: UUID, db: Session) -> dict[str, Any]:
        holdings = self.get_portfolio(player_id, db)
        total_value = sum(h["market_value"] for h in holdings)
        total_cost = sum(h["cost_basis"] for h in holdings)
        return {
            "total_market_value": round(total_value, 2),
            "total_cost_basis": round(total_cost, 2),
            "total_profit_loss": round(total_value - total_cost, 2),
            "holdings_count": len(holdings),
            "holdings": holdings,
        }

    # ── Internal ──────────────────────────────────────────────────────────────

    def _get_current_day(self, db: Session) -> int:
        state = db.query(GameState).order_by(GameState.id.asc()).first()
        return int(state.current_day) if state else 0
