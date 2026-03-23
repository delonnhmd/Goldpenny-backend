"""Marketplace API — Step 8.5 + Step 12.

Multiplayer Marketplace and Player-to-Player Commerce System.

Route overview (Step 8.5 — physical inventory)
----------------------------------------------
GET  /marketplace/listings         — Browse active listings (public, with filters)
POST /marketplace/list             — Authenticated: create Step 8.5 listing from real inventory
POST /marketplace/buy              — Authenticated: purchase Step 8.5 goods from a listing
POST /marketplace/cancel           — Authenticated: cancel own listing, return goods
GET  /marketplace/my-listings      — Authenticated: player's own listings (all steps)
GET  /marketplace/my-transactions  — Authenticated: full Step 8.5 buy/sell history
GET  /marketplace/my-inventory     — Authenticated: player household goods inventory
GET  /marketplace/fees             — Debug: recent Step 8.5 marketplace fee logs

Route overview (Step 12 — abstract goods/services)
---------------------------------------------------
POST /marketplace/listings             — Authenticated: create Step 12 abstract listing
POST /marketplace/purchase             — Authenticated: purchase from a Step 12 listing
GET  /marketplace/my-trades            — Authenticated: Step 12 trade history
GET  /marketplace/me                   — Authenticated: player marketplace profile summary
POST /marketplace/admin/expire-listings — Admin: expire stale Step 12 listings
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.db.database import get_db
from app.engine.marketplace_engine import (
    MarketplaceEngine,
    build_marketplace_summary,
    create_market_listing as s12_create_listing,
    execute_market_purchase,
    expire_s12_listings,
)
from app.models.game_state import GameState
from app.models.market_trade import MarketTrade
from app.models.player import Player
from app.models.user import User

router = APIRouter()
_engine = MarketplaceEngine()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_player_or_404(user: User, db: Session) -> Player:
    player = db.query(Player).filter(Player.user_id == user.id).first()
    if player is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Player profile not found.",
        )
    return player


def _current_day(db: Session) -> int:
    state = db.query(GameState).order_by(GameState.id.asc()).first()
    return int(state.current_day) if state else 1


# ── Request bodies ────────────────────────────────────────────────────────────

class CreateListingRequest(BaseModel):
    source_type: str = Field(
        ...,
        description="'player_inventory' or 'business_inventory'",
    )
    basket_name: str = Field(..., description="Approved basket to list")
    quantity: int = Field(..., ge=1, le=20, description="Units to list (1–20)")
    unit_price: float = Field(..., gt=0, description="Asking price per unit")
    source_business_id: Optional[str] = Field(
        None,
        description="Required when source_type is 'business_inventory'",
    )


class BuyListingRequest(BaseModel):
    listing_id: str = Field(..., description="UUID of the active listing to purchase from")
    quantity: int = Field(..., ge=1, description="Number of units to buy")


class CancelListingRequest(BaseModel):
    listing_id: str = Field(..., description="UUID of the listing to cancel")


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/listings")
def get_listings(
    basket_name: Optional[str] = Query(None, description="Filter by basket type (Step 8.5)"),
    region: Optional[str] = Query(None, description="Filter by seller region"),
    min_price: Optional[float] = Query(None, ge=0, description="Minimum unit price"),
    max_price: Optional[float] = Query(None, ge=0, description="Maximum unit price"),
    listing_type: Optional[str] = Query(
        None, description="Step 12 filter: 'goods' or 'service'"
    ),
    item_id: Optional[str] = Query(None, description="Step 12 filter: item identifier"),
    db: Session = Depends(get_db),
) -> list[dict]:
    """Browse active marketplace listings (Step 8.5 and Step 12).

    Returns all active listings sorted cheapest-first.  Use the optional
    listing_type / item_id query params to filter Step 12 abstract listings.
    Runs expiration check before returning results.
    Public endpoint — no authentication required.
    """
    from app.models.market_listing import MarketListing

    day = _current_day(db)
    # Include Step 12 expiration pass alongside Step 8.5.
    expire_s12_listings(db, day)
    rows = _engine.browse_listings(
        db=db,
        basket_name=basket_name,
        region=region,
        min_price=min_price,
        max_price=max_price,
        current_day=day,
    )
    # Apply Step 12 filters post-query if supplied (browse_listings returns all active).
    if listing_type is not None:
        rows = [r for r in rows if r.get("source_type") == "step12"]
    if item_id is not None:
        rows = [r for r in rows if r.get("basket_name") == item_id or r.get("item_id") == item_id]
    return rows


@router.post("/list")
def create_listing(
    body: CreateListingRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Create a marketplace listing from player or business inventory.

    Inventory is removed from the source immediately to prevent double-spending.
    Approved baskets: essentials_basket, protein_basket, produce_basket,
    convenience_basket.

    Price must be between 70% and 180% of the current market reference price.
    Maximum 5 active listings per player. Maximum 20 units per listing.
    Listing expires after 3 in-game days; unsold goods are returned automatically.
    """
    player = _get_player_or_404(current_user, db)
    day = _current_day(db)
    try:
        return _engine.create_market_listing(
            player=player,
            source_type=body.source_type,
            basket_name=body.basket_name,
            quantity=body.quantity,
            unit_price=body.unit_price,
            current_day=day,
            db=db,
            source_business_id=body.source_business_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post("/buy")
def buy_listing(
    body: BuyListingRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Purchase goods from a marketplace listing.

    Deducts buyer cash.
    Credits seller net proceeds (gross minus 5% fee).
    Adds purchased goods to buyer's household inventory.
    The 5% marketplace fee is sunk from circulation.
    Self-purchasing is blocked unconditionally.
    """
    player = _get_player_or_404(current_user, db)
    day = _current_day(db)
    try:
        return _engine.purchase_market_listing(
            buyer=player,
            listing_id=body.listing_id,
            quantity=body.quantity,
            current_day=day,
            db=db,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post("/cancel")
def cancel_listing(
    body: CancelListingRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Cancel an active listing and return all unsold goods to original inventory.

    Only the listing owner can cancel their own listing.
    Only active listings can be cancelled (not expired or sold-out).
    """
    player = _get_player_or_404(current_user, db)
    try:
        return _engine.cancel_market_listing(
            player=player,
            listing_id=body.listing_id,
            db=db,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get("/my-listings")
def my_listings(
    active_only: bool = Query(False, description="If true, return only active listings"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    """Return the authenticated player's marketplace listings.

    Includes both Step 8.5 physical-inventory listings and Step 12 abstract
    listings.  Set active_only=true to see only currently active listings.
    """
    player = _get_player_or_404(current_user, db)
    listings = _engine.get_my_listings(player, db)
    if active_only:
        listings = [lst for lst in listings if lst.get("listing_status") == "active"]
    return listings


@router.get("/my-transactions")
def my_transactions(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    """Return the authenticated player's full buy and sell transaction history.

    Each record includes a 'role' field: 'buyer' or 'seller'.
    Ordered newest first.
    """
    player = _get_player_or_404(current_user, db)
    return _engine.get_my_transactions(player, db)


@router.get("/my-inventory")
def my_inventory(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    """Return the authenticated player's current household basket goods inventory.

    Shows only baskets with quantity > 0.
    """
    player = _get_player_or_404(current_user, db)
    return _engine.get_player_inventory(player, db)


@router.get("/fees")
def fee_logs(
    limit: int = Query(50, ge=1, le=200, description="Number of recent fee logs to return"),
    db: Session = Depends(get_db),
) -> list[dict]:
    """Return recent Step 8.5 marketplace fee logs.

    Used for economy balancing and debugging. Shows sunk fees per transaction.
    """
    return _engine.get_fee_logs(db=db, limit=limit)


# ═══════════════════════════════════════════════════════════════════════════════
# Step 12 — Abstract Goods / Service Marketplace
# ═══════════════════════════════════════════════════════════════════════════════


class S12CreateListingRequest(BaseModel):
    listing_type: str = Field(..., description="'goods' or 'service'")
    item_id: str = Field(
        ...,
        description=(
            "Goods: essentials | protein | produce | convenience. "
            "Services: mechanic_service | delivery_service | cooking_service."
        ),
    )
    quantity: int = Field(..., ge=1, le=100, description="Units to list (1–100)")
    unit_price_xgp: float = Field(..., gt=0, description="Asking price per unit in XGP")
    display_name: Optional[str] = Field(
        None, description="Optional human-readable label (defaults to item_id)"
    )
    expires_day_number: Optional[int] = Field(
        None, description="In-game day the listing expires (default: current_day + 10)"
    )


class S12PurchaseRequest(BaseModel):
    listing_id: str = Field(..., description="UUID of the Step 12 listing to purchase from")
    quantity: int = Field(..., ge=1, description="Number of units to buy")


@router.post("/listings")
def s12_create_marketplace_listing(
    body: S12CreateListingRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Create a Step 12 abstract goods or service listing.

    No physical inventory is required or consumed.  A non-refundable listing fee
    of 1% of gross listing value (minimum 1.0 XGP) is deducted immediately.

    Goods items: essentials, protein, produce, convenience.
    Service items: mechanic_service, delivery_service, cooking_service.

    Maximum 10 active Step 12 listings per player.  Max quantity per listing: 100.
    Listings expire after 10 in-game days if expires_day_number is not specified.
    """
    player = _get_player_or_404(current_user, db)
    day = _current_day(db)
    try:
        return s12_create_listing(
            db=db,
            seller=player,
            listing_type=body.listing_type,
            item_id=body.item_id,
            quantity=body.quantity,
            unit_price_xgp=body.unit_price_xgp,
            current_day=day,
            expires_day_number=body.expires_day_number,
            display_name=body.display_name,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post("/purchase")
def s12_purchase(
    body: S12PurchaseRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Purchase units from a Step 12 abstract goods or service listing.

    Deducts buyer cash (gross amount).  Credits seller net proceeds (gross minus
    2% market fee).  The 2% fee is sunk from circulation as economic pressure.

    Only Step 12 listings are accepted here.  For Step 8.5 physical-inventory
    listings use POST /marketplace/buy.

    Self-purchasing is unconditionally blocked.
    """
    player = _get_player_or_404(current_user, db)
    day = _current_day(db)
    try:
        return execute_market_purchase(
            db=db,
            buyer=player,
            listing_id=body.listing_id,
            quantity=body.quantity,
            current_day=day,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get("/my-trades")
def my_trades(
    limit: int = Query(50, ge=1, le=200, description="Max records to return"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    """Return the authenticated player's Step 12 trade history (buys and sells).

    Each record includes a role field: 'buyer' or 'seller'.
    Ordered newest first.
    """
    player = _get_player_or_404(current_user, db)
    from sqlalchemy import or_
    trades = (
        db.query(MarketTrade)
        .filter(
            or_(
                MarketTrade.buyer_player_id == player.id,
                MarketTrade.seller_player_id == player.id,
            )
        )
        .order_by(MarketTrade.created_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "trade_id":            str(t.id),
            "listing_id":          str(t.listing_id),
            "listing_type":        t.listing_type,
            "item_id":             t.item_id,
            "quantity":            float(t.quantity),
            "unit_price_xgp":      float(t.unit_price_xgp),
            "gross_amount_xgp":    float(t.gross_amount_xgp),
            "market_fee_xgp":      float(t.market_fee_xgp),
            "seller_net_xgp":      float(t.seller_net_xgp),
            "day_number":          t.day_number,
            "created_at":          t.created_at.isoformat() if t.created_at else None,
            "role":                "buyer" if str(t.buyer_player_id) == str(player.id) else "seller",
        }
        for t in trades
    ]


@router.get("/me")
def marketplace_profile(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Return the authenticated player's Step 12 marketplace profile summary.

    Includes active listing count, completed trade counts, reputation, and
    marketplace rating score.
    """
    player = _get_player_or_404(current_user, db)
    return build_marketplace_summary(db=db, player=player)


@router.post("/admin/expire-listings")
def admin_expire_s12_listings(
    db: Session = Depends(get_db),
) -> dict:
    """Admin: expire all stale Step 12 listings as of the current in-game day.

    This runs automatically during purchase flows, but can also be triggered
    manually by an admin to clean up the marketplace between day cycles.
    Not authenticated in MVP — should be protected by network policy in production.
    """
    day = _current_day(db)
    expired_count = expire_s12_listings(db=db, current_day_number=day)
    return {
        "message": f"Expired {expired_count} stale Step 12 listing(s).",
        "expired_count": expired_count,
        "current_day": day,
    }
