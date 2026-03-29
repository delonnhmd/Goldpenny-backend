"""MVP stock trading service (buy/sell/portfolio/quotes).

This module keeps financial logic out of route handlers and ensures all
trade mutations happen atomically in one DB transaction.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
import logging
from typing import Iterable
from uuid import UUID

from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from app.models.enums import TradeSide
from app.models.player import Player
from app.models.player_stock_holding import PlayerStockHolding
from app.models.stock_daily_price import StockDailyPrice
from app.models.stock_trade_log import StockTradeLog
from app.services.player_transaction_log_service import record_player_transaction

FEE_RATE = Decimal("0.003")
MONEY_Q = Decimal("0.01")
PRICE_Q = Decimal("0.0001")
logger = logging.getLogger(__name__)


class StockTradingError(Exception):
    """Base trading exception."""


class ResourceNotFoundError(StockTradingError):
    """Raised when player/ticker resources cannot be found."""


class ValidationError(StockTradingError):
    """Raised for invalid shares/cash/holding checks."""


def _d(value: object) -> Decimal:
    return Decimal(str(value or 0))


def _money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_Q, rounding=ROUND_HALF_UP)


def _price(value: Decimal) -> Decimal:
    return value.quantize(PRICE_Q, rounding=ROUND_HALF_UP)


def _as_float(value: Decimal) -> float:
    return float(value)


def _normalize_ticker(ticker: str) -> str:
    return (ticker or "").strip().upper()


@dataclass
class Quote:
    ticker: str
    day: int
    sector: str
    close_price: Decimal
    daily_change_pct: Decimal


class StockTradingService:
    """Service-layer stock trading operations."""

    def _get_player(self, db: Session, player_id: UUID | str) -> Player:
        try:
            pid = player_id if isinstance(player_id, UUID) else UUID(str(player_id))
        except ValueError as exc:
            raise ResourceNotFoundError("Player not found.") from exc

        player = db.query(Player).filter(Player.id == pid).first()
        if player is None:
            raise ResourceNotFoundError("Player not found.")
        return player

    def _get_player_for_update(self, db: Session, player_id: UUID | str) -> Player:
        try:
            pid = player_id if isinstance(player_id, UUID) else UUID(str(player_id))
        except ValueError as exc:
            raise ResourceNotFoundError("Player not found.") from exc

        player = (
            db.query(Player)
            .filter(Player.id == pid)
            .with_for_update()
            .first()
        )
        if player is None:
            raise ResourceNotFoundError("Player not found.")
        return player

    def _get_latest_quote_row(self, db: Session, ticker: str) -> StockDailyPrice:
        normalized = _normalize_ticker(ticker)
        row = (
            db.query(StockDailyPrice)
            .filter(StockDailyPrice.ticker == normalized)
            .order_by(StockDailyPrice.day.desc(), StockDailyPrice.created_at.desc())
            .first()
        )
        if row is None:
            raise ResourceNotFoundError(f"Ticker '{normalized}' not found.")
        return row

    def _build_quote(self, row: StockDailyPrice) -> Quote:
        return Quote(
            ticker=row.ticker,
            day=int(row.day),
            sector=row.sector,
            close_price=_price(_d(row.close_price)),
            daily_change_pct=_price(_d(row.daily_change_pct)),
        )

    def get_latest_quote(self, db: Session, ticker: str) -> dict:
        row = self._get_latest_quote_row(db, ticker)
        quote = self._build_quote(row)
        return {
            "ticker": quote.ticker,
            "latest_day": quote.day,
            "sector": quote.sector,
            "close_price": _as_float(quote.close_price),
            "daily_change_pct": _as_float(quote.daily_change_pct),
        }

    def get_all_latest_quotes(self, db: Session) -> list[dict]:
        latest_day_by_ticker = (
            db.query(
                StockDailyPrice.ticker.label("ticker"),
                func.max(StockDailyPrice.day).label("latest_day"),
            )
            .group_by(StockDailyPrice.ticker)
            .subquery()
        )

        rows = (
            db.query(StockDailyPrice)
            .join(
                latest_day_by_ticker,
                and_(
                    StockDailyPrice.ticker == latest_day_by_ticker.c.ticker,
                    StockDailyPrice.day == latest_day_by_ticker.c.latest_day,
                ),
            )
            .order_by(StockDailyPrice.ticker.asc())
            .all()
        )

        return [self.get_latest_quote(db, row.ticker) for row in rows]

    # Backward-compatible aliases used by older route code paths.
    def get_market_quote(self, db: Session, ticker: str) -> dict:
        return self.get_latest_quote(db, ticker)

    def get_all_market_quotes(self, db: Session) -> list[dict]:
        return self.get_all_latest_quotes(db)

    def _validate_shares(self, shares: int) -> None:
        if not isinstance(shares, int):
            raise ValidationError("shares must be an integer.")
        if shares <= 0:
            raise ValidationError("shares must be greater than 0.")

    def buy_stock(self, db: Session, player_id: UUID | str, ticker: str, shares: int) -> dict:
        self._validate_shares(shares)
        normalized_ticker = _normalize_ticker(ticker)

        try:
            player = self._get_player_for_update(db, player_id)
            quote_row = self._get_latest_quote_row(db, normalized_ticker)
            quote = self._build_quote(quote_row)

            execution_price = quote.close_price
            gross_amount = _money(execution_price * Decimal(shares))
            fee_amount = _money(gross_amount * FEE_RATE)
            total_cost = _money(gross_amount + fee_amount)

            cash_before = _money(_d(player.cash_xgp))
            if cash_before < total_cost:
                raise ValidationError(
                    f"Insufficient cash. Need {total_cost}, have {cash_before}."
                )

            holding = (
                db.query(PlayerStockHolding)
                .filter(
                    PlayerStockHolding.player_id == player.id,
                    PlayerStockHolding.stock_id == normalized_ticker,
                )
                .with_for_update()
                .first()
            )
            if holding is None:
                holding = PlayerStockHolding(
                    player_id=player.id,
                    stock_id=normalized_ticker,
                    shares_owned=0,
                    average_cost_basis=Decimal("0"),
                    total_cost_basis=Decimal("0"),
                )
                db.add(holding)
                db.flush()

            old_shares = int(holding.shares_owned or 0)
            old_avg = _price(_d(holding.average_cost_basis))
            new_shares = old_shares + shares
            weighted_total = (old_avg * Decimal(old_shares)) + (execution_price * Decimal(shares))
            new_average_cost_basis = _price(weighted_total / Decimal(new_shares))

            holding.shares_owned = new_shares
            holding.average_cost_basis = new_average_cost_basis
            holding.total_cost_basis = _money(new_average_cost_basis * Decimal(new_shares))

            remaining_cash = _money(cash_before - total_cost)
            player.cash_xgp = remaining_cash

            trade_log = StockTradeLog(
                player_id=player.id,
                day=quote.day,
                ticker=normalized_ticker,
                side=TradeSide.buy,
                shares=shares,
                price_per_share=execution_price,
                gross_amount_xgp=gross_amount,
                fee_amount_xgp=fee_amount,
                net_amount_xgp=total_cost,
                realized_pnl_xgp=None,
            )
            db.add(trade_log)

            # Unified transaction history (Step 73): trade row + explicit fee row.
            record_player_transaction(
                db,
                player=player,
                day=quote.day,
                transaction_type="stock_buy",
                category="stock_market",
                asset_symbol=normalized_ticker,
                quantity=shares,
                unit_price=execution_price,
                gross_amount=gross_amount,
                fee_amount=fee_amount,
                net_cash_delta=-total_cost,
                resulting_cash_balance=remaining_cash,
                metadata={
                    "trade_side": "buy",
                    "fee_rate": str(FEE_RATE),
                    "shares_after": new_shares,
                },
            )
            if fee_amount > Decimal("0.00"):
                record_player_transaction(
                    db,
                    player=player,
                    day=quote.day,
                    transaction_type="fee",
                    category="stock_market",
                    asset_symbol=normalized_ticker,
                    quantity=shares,
                    unit_price=execution_price,
                    gross_amount=fee_amount,
                    fee_amount=Decimal("0.00"),
                    net_cash_delta=Decimal("0.00"),
                    resulting_cash_balance=remaining_cash,
                    metadata={"fee_source": "stock_buy", "fee_rate": str(FEE_RATE)},
                )

            logger.info(
                "stocks.buy committed atomically.",
                extra={
                    "player_id": str(player.id),
                    "ticker": normalized_ticker,
                    "shares": shares,
                    "cash_before": float(cash_before),
                    "cash_after": float(remaining_cash),
                    "gross_amount": float(gross_amount),
                    "fee_amount": float(fee_amount),
                },
            )

            db.commit()
            db.refresh(player)
            db.refresh(holding)

            return {
                "player_id": str(player.id),
                "ticker": normalized_ticker,
                "shares_bought": shares,
                "execution_price": _as_float(execution_price),
                "gross_amount": _as_float(gross_amount),
                "fee_amount": _as_float(fee_amount),
                "total_cost": _as_float(total_cost),
                "remaining_cash": _as_float(_money(_d(player.cash_xgp))),
                "updated_holding_shares": int(holding.shares_owned),
                "updated_average_cost_basis": _as_float(_price(_d(holding.average_cost_basis))),
            }
        except StockTradingError:
            db.rollback()
            raise
        except Exception as exc:
            db.rollback()
            raise StockTradingError("Unexpected error while buying stock.") from exc

    def sell_stock(self, db: Session, player_id: UUID | str, ticker: str, shares: int) -> dict:
        self._validate_shares(shares)
        normalized_ticker = _normalize_ticker(ticker)

        try:
            player = self._get_player_for_update(db, player_id)
            quote_row = self._get_latest_quote_row(db, normalized_ticker)
            quote = self._build_quote(quote_row)

            holding = (
                db.query(PlayerStockHolding)
                .filter(
                    PlayerStockHolding.player_id == player.id,
                    PlayerStockHolding.stock_id == normalized_ticker,
                )
                .with_for_update()
                .first()
            )
            if holding is None:
                raise ValidationError(f"Insufficient shares. No holding for '{normalized_ticker}'.")

            held_shares = int(holding.shares_owned or 0)
            if held_shares < shares:
                raise ValidationError(
                    f"Insufficient shares. Tried to sell {shares}, but only {held_shares} available."
                )

            execution_price = quote.close_price
            gross_amount = _money(execution_price * Decimal(shares))
            fee_amount = _money(gross_amount * FEE_RATE)
            net_amount = _money(gross_amount - fee_amount)

            average_cost = _price(_d(holding.average_cost_basis))
            realized_pnl = _money(((execution_price - average_cost) * Decimal(shares)) - fee_amount)

            cash_before = _money(_d(player.cash_xgp))
            remaining_cash = _money(cash_before + net_amount)
            player.cash_xgp = remaining_cash

            remaining_holding_shares = held_shares - shares
            if remaining_holding_shares == 0:
                # MVP policy: remove empty positions on full sell.
                db.delete(holding)
            else:
                holding.shares_owned = remaining_holding_shares
                holding.total_cost_basis = _money(average_cost * Decimal(remaining_holding_shares))

            trade_log = StockTradeLog(
                player_id=player.id,
                day=quote.day,
                ticker=normalized_ticker,
                side=TradeSide.sell,
                shares=shares,
                price_per_share=execution_price,
                gross_amount_xgp=gross_amount,
                fee_amount_xgp=fee_amount,
                net_amount_xgp=net_amount,
                realized_pnl_xgp=realized_pnl,
            )
            db.add(trade_log)

            record_player_transaction(
                db,
                player=player,
                day=quote.day,
                transaction_type="stock_sell",
                category="stock_market",
                asset_symbol=normalized_ticker,
                quantity=shares,
                unit_price=execution_price,
                gross_amount=gross_amount,
                fee_amount=fee_amount,
                net_cash_delta=net_amount,
                resulting_cash_balance=remaining_cash,
                metadata={
                    "trade_side": "sell",
                    "fee_rate": str(FEE_RATE),
                    "shares_after": remaining_holding_shares,
                    "realized_pnl_xgp": str(realized_pnl),
                },
            )
            if fee_amount > Decimal("0.00"):
                record_player_transaction(
                    db,
                    player=player,
                    day=quote.day,
                    transaction_type="fee",
                    category="stock_market",
                    asset_symbol=normalized_ticker,
                    quantity=shares,
                    unit_price=execution_price,
                    gross_amount=fee_amount,
                    fee_amount=Decimal("0.00"),
                    net_cash_delta=Decimal("0.00"),
                    resulting_cash_balance=remaining_cash,
                    metadata={"fee_source": "stock_sell", "fee_rate": str(FEE_RATE)},
                )

            logger.info(
                "stocks.sell committed atomically.",
                extra={
                    "player_id": str(player.id),
                    "ticker": normalized_ticker,
                    "shares": shares,
                    "cash_before": float(cash_before),
                    "cash_after": float(remaining_cash),
                    "gross_amount": float(gross_amount),
                    "fee_amount": float(fee_amount),
                    "remaining_holding_shares": remaining_holding_shares,
                },
            )

            db.commit()
            db.refresh(player)
            if remaining_holding_shares > 0:
                db.refresh(holding)

            return {
                "player_id": str(player.id),
                "ticker": normalized_ticker,
                "shares_sold": shares,
                "execution_price": _as_float(execution_price),
                "gross_amount": _as_float(gross_amount),
                "fee_amount": _as_float(fee_amount),
                "net_amount": _as_float(net_amount),
                "realized_pnl": _as_float(realized_pnl),
                "remaining_cash": _as_float(_money(_d(player.cash_xgp))),
                "remaining_holding_shares": remaining_holding_shares,
            }
        except StockTradingError:
            db.rollback()
            raise
        except Exception as exc:
            db.rollback()
            raise StockTradingError("Unexpected error while selling stock.") from exc

    def _latest_quote_map(self, db: Session, tickers: Iterable[str]) -> dict[str, Decimal]:
        ticker_list = [_normalize_ticker(t) for t in tickers]
        if not ticker_list:
            return {}

        latest_day_by_ticker = (
            db.query(
                StockDailyPrice.ticker.label("ticker"),
                func.max(StockDailyPrice.day).label("latest_day"),
            )
            .filter(StockDailyPrice.ticker.in_(ticker_list))
            .group_by(StockDailyPrice.ticker)
            .subquery()
        )

        rows = (
            db.query(StockDailyPrice)
            .join(
                latest_day_by_ticker,
                and_(
                    StockDailyPrice.ticker == latest_day_by_ticker.c.ticker,
                    StockDailyPrice.day == latest_day_by_ticker.c.latest_day,
                ),
            )
            .all()
        )
        return {row.ticker: _price(_d(row.close_price)) for row in rows}

    def get_player_portfolio(self, db: Session, player_id: UUID | str) -> dict:
        player = self._get_player(db, player_id)
        cash = _money(_d(player.cash_xgp))

        holdings = (
            db.query(PlayerStockHolding)
            .filter(
                PlayerStockHolding.player_id == player.id,
                PlayerStockHolding.shares_owned > 0,
            )
            .order_by(PlayerStockHolding.stock_id.asc())
            .all()
        )

        latest_prices = self._latest_quote_map(db, (h.stock_id for h in holdings))

        holdings_out: list[dict] = []
        total_market_value = Decimal("0")
        total_cost_basis = Decimal("0")
        total_unrealized_pnl = Decimal("0")

        for holding in holdings:
            ticker = _normalize_ticker(holding.stock_id)
            shares = int(holding.shares_owned or 0)
            avg_cost = _price(_d(holding.average_cost_basis))
            latest_price = _price(latest_prices.get(ticker, Decimal("0")))

            market_value = _money(latest_price * Decimal(shares))
            cost_basis = _money(avg_cost * Decimal(shares))
            unrealized_pnl = _money(market_value - cost_basis)

            total_market_value += market_value
            total_cost_basis += cost_basis
            total_unrealized_pnl += unrealized_pnl

            holdings_out.append(
                {
                    "ticker": ticker,
                    "shares": shares,
                    "average_cost_basis": _as_float(avg_cost),
                    "latest_price": _as_float(latest_price),
                    "market_value": _as_float(market_value),
                    "unrealized_pnl": _as_float(unrealized_pnl),
                }
            )

        return {
            "player_id": str(player.id),
            "cash_xgp": _as_float(cash),
            "total_market_value": _as_float(_money(total_market_value)),
            "total_cost_basis": _as_float(_money(total_cost_basis)),
            "total_unrealized_pnl": _as_float(_money(total_unrealized_pnl)),
            "holdings": holdings_out,
        }
