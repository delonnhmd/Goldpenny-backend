"""Stocks API — Step 6 (legacy) + Step 9 (sector stock system).

Step 6 routes (legacy, old models):
GET  /stocks/list                    — All stocks with live price and daily change
GET  /stocks/portfolio               — Authenticated player's holdings and P&L
GET  /stocks/trades                  — Authenticated player's trade history
GET  /stocks/{symbol}                — Single stock detail
POST /stocks/buy                     — Disabled for V1
POST /stocks/sell                    — Disabled for V1
POST /stocks/seed                    — Admin: seed initial stock catalog
POST /stocks/update-prices           — Admin: manually trigger daily price update

Step 9 routes (new sector stock system):
GET  /stocks/sector-list             — All active SectorStocks with live price
GET  /stocks/sector-history          — StockPriceHistory, newest first
POST /stocks/admin/apply-daily-update — Idempotent daily price update for one day
POST /stocks/trade                   — Disabled for V1
GET  /stocks/sector-portfolio        — Authenticated player sector holdings + P&L
GET  /stocks/trade-history           — Authenticated player sector trade log
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.db.database import get_db
from app.engine.stock_engine import (
    StockEngine,
    apply_daily_stock_price_update,
    build_sector_portfolio_summary,
    process_stock_trade,
)
from app.models.economy import EconomyState
from app.models.player import Player
from app.models.sector_index import SectorIndex
from app.models.sector_stock import SectorStock
from app.models.stock import Stock
from app.models.stock_price_history import StockPriceHistory
from app.models.stock_trade import StockTrade
from app.models.trade import Trade
from app.models.user import User
from app.services.stock_trading_service import (
    ResourceNotFoundError,
    StockTradingError,
    StockTradingService,
    ValidationError,
)

router = APIRouter()
_engine = StockEngine()
_stock_trading_service = StockTradingService()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_player_or_404(user: User, db: Session) -> Player:
    player = db.query(Player).filter(Player.user_id == str(user.id)).first()
    if player is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Player profile not found.")
    return player


def _latest_day(db: Session) -> int:
    state = db.query(EconomyState).order_by(EconomyState.day.desc()).first()
    return state.day if state else 0


def _daily_change_for(symbol: str, sector: str, db: Session, day: int) -> float:
    """Return the sector daily change % for the latest day as a price change proxy."""
    row = (
        db.query(SectorIndex)
        .filter(SectorIndex.sector_name == sector, SectorIndex.day == day)
        .first()
    )
    return row.daily_change_percent if row else 0.0


# ── Request bodies ────────────────────────────────────────────────────────────

class TradeRequest(BaseModel):
    symbol: str
    shares: int


class StockOrderRequest(BaseModel):
    player_id: str
    ticker: str
    shares: int


def _raise_service_http_error(exc: Exception) -> None:
    if isinstance(exc, ResourceNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, ValidationError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Unexpected stock trading error.",
    )


# ── GET /stocks/list ──────────────────────────────────────────────────────────

@router.get("/list")
def list_stocks(db: Session = Depends(get_db)) -> list[dict]:
    """Return all available stocks with live price and sector daily change."""
    stocks = db.query(Stock).order_by(Stock.sector, Stock.symbol).all()
    latest = _latest_day(db)
    result = []
    for s in stocks:
        daily_change = _daily_change_for(s.symbol, s.sector, db, latest)
        result.append(
            {
                "symbol": s.symbol,
                "company_name": s.company_name or s.name,
                "sector": s.sector,
                "current_price": float(s.current_price),
                "base_price": float(s.base_price),
                "daily_change_percent": round(daily_change, 4),
                "volatility": s.volatility,
                "growth_bias": s.growth_bias,
            }
        )
    return result


# ── GET /stocks/portfolio ─────────────────────────────────────────────────────

@router.get("/portfolio")
def get_portfolio(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Return the authenticated player's stock portfolio and P&L summary."""
    player = _get_player_or_404(current_user, db)
    return _engine.get_portfolio_summary(player.id, db)


# ── GET /stocks/trades ────────────────────────────────────────────────────────

@router.get("/trades")
def get_legacy_trade_history(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    """Return the authenticated player's trade history, newest first."""
    player = _get_player_or_404(current_user, db)
    trades = (
        db.query(Trade)
        .filter(Trade.player_id == player.id)
        .order_by(Trade.created_at.desc())
        .limit(100)
        .all()
    )
    return [
        {
            "id": str(t.id),
            "symbol": t.stock_symbol,
            "trade_type": t.trade_type,
            "shares": t.shares,
            "price_per_share": float(t.price_per_share),
            "total_value": float(t.total_value),
            "day": t.day,
            "created_at": t.created_at.isoformat() if t.created_at else None,
        }
        for t in trades
    ]


# ── GET /stocks/{symbol} ──────────────────────────────────────────────────────

@router.get("/quotes")
def get_latest_quotes(db: Session = Depends(get_db)) -> dict:
    """Return the latest available close-price snapshot for all tickers."""
    quotes = _stock_trading_service.get_all_latest_quotes(db)
    return {"count": len(quotes), "quotes": quotes}


@router.get("/quotes/{ticker}")
def get_quote_by_ticker(ticker: str, db: Session = Depends(get_db)) -> dict:
    """Return the latest available quote for one ticker."""
    try:
        return _stock_trading_service.get_latest_quote(db, ticker)
    except (ResourceNotFoundError, ValidationError, StockTradingError) as exc:
        _raise_service_http_error(exc)
    except Exception as exc:
        _raise_service_http_error(StockTradingError(str(exc)))


@router.get("/portfolio/{player_id}")
def get_player_portfolio(player_id: str, db: Session = Depends(get_db)) -> dict:
    """Return player cash, holdings, market value, and P&L summary."""
    try:
        return _stock_trading_service.get_player_portfolio(db, player_id)
    except (ResourceNotFoundError, ValidationError, StockTradingError) as exc:
        _raise_service_http_error(exc)
    except Exception as exc:
        _raise_service_http_error(StockTradingError(str(exc)))


# ── POST /stocks/buy ──────────────────────────────────────────────────────────

@router.post("/buy")
def buy_stock(
    body: StockOrderRequest,
    db: Session = Depends(get_db),
) -> dict:
    """Execute a market buy at the latest available close price."""
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail="Stock trading is frozen for V1.",
    )


# ── POST /stocks/sell ─────────────────────────────────────────────────────────

@router.post("/sell")
def sell_stock(
    body: StockOrderRequest,
    db: Session = Depends(get_db),
) -> dict:
    """Execute a market sell at the latest available close price."""
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail="Stock trading is frozen for V1.",
    )


# ── POST /stocks/seed ─────────────────────────────────────────────────────────

@router.post("/legacy/buy")
def legacy_buy_stock(
    body: TradeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Legacy authenticated buy endpoint retained for backward compatibility."""
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail="Stock trading is frozen for V1.",
    )


@router.post("/legacy/sell")
def legacy_sell_stock(
    body: TradeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Legacy authenticated sell endpoint retained for backward compatibility."""
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail="Stock trading is frozen for V1.",
    )


@router.post("/seed")
def seed_stocks(db: Session = Depends(get_db)) -> dict:
    """Admin: seed initial stock catalog. Safe to call repeatedly (idempotent)."""
    seeded = _engine.seed_stocks(db)
    return {
        "message": f"Seeded {len(seeded)} new stock(s).",
        "seeded_symbols": seeded,
    }


# ── POST /stocks/update-prices ────────────────────────────────────────────────

@router.post("/update-prices")
def update_prices(db: Session = Depends(get_db)) -> dict:
    """Admin: trigger a manual daily price update for the latest economy day."""
    latest = _latest_day(db)
    if latest == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No economy day processed yet. Call POST /economy/process-next-day first.",
        )
    updates = _engine.update_daily_stock_prices(latest, db)
    return {
        "message": f"Prices updated for day {latest}.",
        "day": latest,
        "stocks_updated": len(updates),
        "updates": updates,
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# STEP 9 — Sector Stock System Routes
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


# ── Request bodies ─────────────────────────────────────────────────────────────

class SectorTradeRequest(BaseModel):
    stock_id: str
    trade_type: str   # "buy" | "sell"
    shares: int


class ApplyDailyUpdateRequest(BaseModel):
    day_number: int


# ── GET /stocks/sector-list ───────────────────────────────────────────────────

@router.get("/sector-list")
def list_sector_stocks(db: Session = Depends(get_db)) -> dict:
    """Return all active SectorStocks with their current price and sensitivities."""
    stocks = (
        db.query(SectorStock)
        .filter(SectorStock.is_active.is_(True))
        .order_by(SectorStock.sector_type, SectorStock.stock_id)
        .all()
    )
    return {
        "count": len(stocks),
        "stocks": [
            {
                "stock_id": s.stock_id,
                "display_name": s.display_name,
                "sector_type": s.sector_type,
                "current_price": float(s.current_price),
                "is_active": s.is_active,
                "confidence_sensitivity": float(s.confidence_sensitivity),
                "inflation_sensitivity": float(s.inflation_sensitivity),
                "oil_sensitivity": float(s.oil_sensitivity),
                "unemployment_sensitivity": float(s.unemployment_sensitivity),
                "interest_rate_sensitivity": float(s.interest_rate_sensitivity),
            }
            for s in stocks
        ],
    }


# ── GET /stocks/sector-history ────────────────────────────────────────────────

@router.get("/sector-history")
def get_sector_price_history(
    stock_id: str | None = Query(None, description="Filter by stock_id"),
    day_number: int | None = Query(None, description="Filter by exact day number"),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> dict:
    """Return StockPriceHistory rows, newest first.

    Optional filters: stock_id, day_number.  Max 500 rows.
    """
    q = db.query(StockPriceHistory)
    if stock_id is not None:
        q = q.filter(StockPriceHistory.stock_id == stock_id)
    if day_number is not None:
        q = q.filter(StockPriceHistory.day_number == day_number)

    rows = (
        q.order_by(
            StockPriceHistory.day_number.desc(),
            StockPriceHistory.stock_id.asc(),
        )
        .limit(limit)
        .all()
    )

    return {
        "count": len(rows),
        "history": [
            {
                "stock_id": r.stock_id,
                "day_number": r.day_number,
                "old_price": float(r.old_price),
                "new_price": float(r.new_price),
                "change_percent": float(r.change_percent),
                "inflation_used": float(r.inflation_used),
                "interest_rate_used": float(r.interest_rate_used),
                "unemployment_used": float(r.unemployment_used),
                "oil_index_used": float(r.oil_index_used),
                "consumer_confidence_used": float(r.consumer_confidence_used),
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ],
    }


# ── POST /stocks/admin/apply-daily-update ─────────────────────────────────────

@router.post("/admin/apply-daily-update")
def admin_apply_daily_update(
    body: ApplyDailyUpdateRequest,
    db: Session = Depends(get_db),
) -> dict:
    """Admin: idempotent daily price update for all active SectorStocks.

    Skips stocks that already have a StockPriceHistory row for *day_number*.
    Safe to call multiple times for the same day.
    """
    written = apply_daily_stock_price_update(db, body.day_number)
    return {
        "message": f"Daily stock update applied for day {body.day_number}.",
        "day_number": body.day_number,
        "stocks_updated": len(written),
        "updated_stock_ids": [h.stock_id for h in written],
    }


# ── POST /stocks/trade ────────────────────────────────────────────────────────

@router.post("/trade")
def trade_sector_stock(
    body: SectorTradeRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Buy or sell shares in a SectorStock.

    Fee: 0.3% of gross trade value.
    BUY:  player pays  gross + fee.
    SELL: player receives gross - fee.
    """
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail="Stock trading is frozen for V1.",
    )


# ── GET /stocks/sector-portfolio ──────────────────────────────────────────────

@router.get("/sector-portfolio")
def get_sector_portfolio(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Return the authenticated player's SectorStock holdings and unrealised P&L."""
    player = _get_player_or_404(user, db)
    summary = build_sector_portfolio_summary(db, player)
    return summary


# ── GET /stocks/trade-history ─────────────────────────────────────────────────

@router.get("/trade-history")
def get_trade_history(
    limit: int = Query(50, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Return the authenticated player's StockTrade log, newest first."""
    player = _get_player_or_404(user, db)
    trades = (
        db.query(StockTrade)
        .filter(StockTrade.player_id == player.id)
        .order_by(StockTrade.created_at.desc())
        .limit(limit)
        .all()
    )
    return {
        "count": len(trades),
        "trades": [
            {
                "id": str(t.id),
                "stock_id": t.stock_id,
                "day_number": t.day_number,
                "trade_type": t.trade_type,
                "shares": t.shares,
                "price_per_share": float(t.price_per_share),
                "gross_amount": float(t.gross_amount),
                "transaction_fee": float(t.transaction_fee),
                "net_amount": float(t.net_amount),
                "balance_before": float(t.balance_before),
                "balance_after": float(t.balance_after),
                "created_at": t.created_at.isoformat() if t.created_at else None,
            }
            for t in trades
        ],
    }


@router.get("/{symbol}")
def get_stock(symbol: str, db: Session = Depends(get_db)) -> dict:
    """Return full info for a single legacy stock symbol."""
    stock = db.query(Stock).filter(Stock.symbol == symbol.upper()).first()
    if stock is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Stock '{symbol}' not found.")
    latest = _latest_day(db)
    daily_change = _daily_change_for(stock.symbol, stock.sector, db, latest)
    return {
        "symbol": stock.symbol,
        "company_name": stock.company_name or stock.name,
        "sector": stock.sector,
        "base_price": float(stock.base_price),
        "current_price": float(stock.current_price),
        "daily_change_percent": round(daily_change, 4),
        "volatility": stock.volatility,
        "growth_bias": stock.growth_bias,
        "created_at": stock.created_at.isoformat() if stock.created_at else None,
    }
