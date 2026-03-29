"""Marketplace Engine — Step 8.5.

All player-to-player marketplace logic lives here.
API routes must stay thin — call engine methods and handle ValueError → HTTP 400.

Design rules
------------
- No goods or money are created from nothing.
- All listings must come from verifiable, real inventory.
- Inventory is removed from source immediately at listing creation.
- Cancellation / expiration returns goods to the original source.
- Every completed transaction incurs a 5% fee sunk from circulation.
- Self-buying is unconditionally blocked.
- Suspicious trading patterns are logged but not auto-acted upon in MVP.
- All cash arithmetic uses Decimal with ROUND_HALF_UP.
"""

from __future__ import annotations

import uuid as _uuid_module
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.business import Business
from app.models.business_inventory import BusinessInventory
from app.models.economy import EconomyState
from app.models.game_state import GameState
from app.models.market_fee_log import MarketFeeLog
from app.models.market_listing import MarketListing
from app.models.market_transaction import MarketTransaction
from app.models.player import Player
from app.models.player_inventory import PlayerInventory
# Step 12: abstract marketplace imports
from app.models.contribution_event import ContributionEvent
from app.models.market_trade import MarketTrade
from app.models.xgp_transaction import XGPTransaction

# ── Constants ─────────────────────────────────────────────────────────────────

# Only these basket types may be listed on the marketplace (MVP scope).
_APPROVED_BASKETS: frozenset[str] = frozenset({
    "essentials_basket",
    "protein_basket",
    "produce_basket",
    "convenience_basket",
})

# Base reference prices used for listing guardrails (before inflation adjustment).
_BASKET_BASE_PRICES: dict[str, Decimal] = {
    "essentials_basket": Decimal("15.00"),
    "protein_basket": Decimal("12.00"),
    "produce_basket": Decimal("10.00"),
    "convenience_basket": Decimal("8.00"),
}

_MARKETPLACE_FEE_RATE = Decimal("0.05")        # 5% of gross total, sunk
_MAX_ACTIVE_LISTINGS_PER_PLAYER = 5
_MAX_QUANTITY_PER_LISTING = 20
_DEFAULT_LISTING_DAYS = 3                       # listing expires after 3 in-game days
_MIN_PRICE_FACTOR = Decimal("0.70")            # floor: 70% of reference price
_MAX_PRICE_FACTOR = Decimal("1.80")            # ceiling: 180% of reference price

# Suspicious pair threshold: same buyer-seller pair within a single day.
_SUSPICIOUS_PAIR_THRESHOLD = 3

_D = Decimal

# ── Step 12 constants ────────────────────────────────────────────────────────

VALID_GOODS_ITEMS: frozenset[str] = frozenset({
    "essentials",
    "protein",
    "produce",
    "convenience",
})

VALID_SERVICE_ITEMS: frozenset[str] = frozenset({
    "mechanic_service",
    "delivery_service",
    "cooking_service",
})

_S12_LISTING_FEE_RATE     = Decimal("0.01")   # 1% of gross listing value, min 1.0 XGP
_S12_MARKET_FEE_RATE      = Decimal("0.02")   # 2% of gross purchase amount (sunk)
_S12_DEFAULT_LISTING_DAYS = 10                 # abstract listings expire after 10 game days
_S12_MAX_LISTINGS          = 10                # Step 12 active-listing cap per player


def _s12_money(val: Any) -> Decimal:
    return Decimal(str(val)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# ── Step 12 public helper functions ──────────────────────────────────────────

def validate_listing_type_and_item(
    listing_type: str,
    item_id: str,
) -> tuple[bool, str | None]:
    """Validate listing_type / item_id pair for Step 12 abstract listings.

    Returns (True, None) on success, (False, error_message) on failure.
    """
    if listing_type not in ("goods", "service"):
        return False, f"listing_type must be 'goods' or 'service', got '{listing_type}'."
    if listing_type == "goods" and item_id not in VALID_GOODS_ITEMS:
        return False, (
            f"item_id '{item_id}' is not a valid goods item. "
            f"Valid options: {sorted(VALID_GOODS_ITEMS)}."
        )
    if listing_type == "service" and item_id not in VALID_SERVICE_ITEMS:
        return False, (
            f"item_id '{item_id}' is not a valid service item. "
            f"Valid options: {sorted(VALID_SERVICE_ITEMS)}."
        )
    return True, None


def calculate_listing_fee(unit_price_xgp: float, quantity: int) -> float:
    """Compute the 1% upfront listing fee (minimum 1.0 XGP).

    Non-refundable — designed to deter spam listings.
    """
    gross   = _s12_money(Decimal(str(unit_price_xgp))) * _D(str(quantity))
    raw_fee = _s12_money(gross * _S12_LISTING_FEE_RATE)
    return float(max(raw_fee, Decimal("1.00")))


def calculate_market_transaction_fee(gross_amount_xgp: float) -> float:
    """Compute the 2% market fee sunk from every Step 12 sale."""
    return float(_s12_money(Decimal(str(gross_amount_xgp)) * _S12_MARKET_FEE_RATE))


# ── Step 12 engine functions ─────────────────────────────────────────────────

def create_market_listing(
    db: Session,
    seller: Player,
    listing_type: str,
    item_id: str,
    quantity: int,
    unit_price_xgp: float,
    current_day: int,
    expires_day_number: int | None = None,
    display_name: str | None = None,
) -> dict[str, Any]:
    """Create a Step 12 abstract goods or service listing.

    No physical inventory is consumed.  A non-refundable listing fee of
    1% of gross listing value (minimum 1.0 XGP) is deducted immediately.
    Raises ValueError on any validation failure.
    """
    ok, err = validate_listing_type_and_item(listing_type, item_id)
    if not ok:
        raise ValueError(err)

    if quantity <= 0:
        raise ValueError("Quantity must be at least 1.")
    if quantity > 100:
        raise ValueError("Maximum quantity per listing is 100.")

    unit_price_d = _s12_money(unit_price_xgp)
    if unit_price_d <= Decimal("0"):
        raise ValueError("Unit price must be greater than zero.")
    if unit_price_d > Decimal("99999.99"):
        raise ValueError("Unit price must not exceed 99,999.99 XGP.")

    # Active listing cap (Step 12 only).
    s12_active = (
        db.query(MarketListing)
        .filter(
            MarketListing.seller_player_id == seller.id,
            MarketListing.listing_status == "active",
            MarketListing.listing_type.isnot(None),
        )
        .count()
    )
    if s12_active >= _S12_MAX_LISTINGS:
        raise ValueError(
            f"You already have {s12_active} active Step 12 listings. "
            f"Maximum is {_S12_MAX_LISTINGS}."
        )

    listing_fee   = _s12_money(calculate_listing_fee(float(unit_price_d), quantity))
    seller_cash   = _s12_money(seller.cash)
    if seller_cash < listing_fee:
        raise ValueError(
            f"Insufficient funds. Listing fee is {listing_fee} XGP, "
            f"your balance is {seller_cash} XGP."
        )

    balance_before = seller_cash
    seller.cash    = seller_cash - listing_fee
    balance_after  = _s12_money(seller.cash)

    db.add(XGPTransaction(
        player_id=seller.id,
        transaction_type="market_listing_fee",
        direction="out",
        amount=listing_fee,
        balance_before=balance_before,
        balance_after=balance_after,
        reference_type="market_listing",
        description=(
            f"Step 12 listing fee: {quantity}\u00d7 {item_id} @ {unit_price_d} XGP"
        ),
    ))
    db.add(ContributionEvent(
        player_id=seller.id,
        event_type="market_listing",
        xgp_value=float(listing_fee),
        event_units=1.0,
    ))

    expires_day  = (
        expires_day_number
        if expires_day_number is not None
        else current_day + _S12_DEFAULT_LISTING_DAYS
    )
    basket_label = display_name or item_id
    listing = MarketListing(
        seller_player_id=seller.id,
        source_type="step12",
        basket_name=basket_label,
        listing_type=listing_type,
        item_id=item_id,
        quantity_total=quantity,
        quantity_remaining=quantity,
        unit_price=unit_price_d,
        listing_status="active",
        listing_fee_xgp=listing_fee,
        region=getattr(seller, "region", "suburban") or "suburban",
        created_day=current_day,
        expires_day=expires_day,
    )
    db.add(listing)
    db.commit()
    db.refresh(listing)

    return {
        "message":           "Listing created.",
        "listing_id":        str(listing.id),
        "listing_type":      listing_type,
        "item_id":           item_id,
        "quantity":          quantity,
        "unit_price_xgp":    float(unit_price_d),
        "listing_fee_xgp":   float(listing_fee),
        "seller_balance_after": float(seller.cash),
        "expires_day":       expires_day,
        "listing_status":    "active",
    }


def execute_market_purchase(
    db: Session,
    buyer: Player,
    listing_id: str,
    quantity: int,
    current_day: int,
) -> dict[str, Any]:
    """Execute a Step 12 marketplace purchase.

    Flow:
    1. Expire stale Step 12 listings.
    2. Validate listing is a Step 12 listing, active, not self-buy.
    3. Validate quantity and buyer cash.
    4. Compute gross, 2% market fee, seller net.
    5. Transfer cash (buyer out, seller in); fee is sunk.
    6. Update listing quantity_remaining; mark sold_out if depleted.
    7. Record MarketTrade, XGPTransactions, ContributionEvents.
    8. Update seller reputation metrics.
    9. Commit and return summary.

    Raises ValueError on any validation failure.
    """
    expire_s12_listings(db, current_day)

    try:
        listing_uuid = _uuid_module.UUID(listing_id)
    except (ValueError, AttributeError):
        raise ValueError("Invalid listing_id format.")

    listing = db.query(MarketListing).filter(MarketListing.id == listing_uuid).first()
    if listing is None:
        raise ValueError("Listing not found.")
    if listing.listing_type is None:
        raise ValueError(
            "This is a Step 8.5 inventory listing. "
            "Use POST /marketplace/buy to purchase it."
        )
    if listing.listing_status != "active":
        raise ValueError(f"Listing is not active (status: '{listing.listing_status}').")
    if str(listing.seller_player_id) == str(buyer.id):
        raise ValueError("You cannot purchase your own listing.")

    if quantity <= 0:
        raise ValueError("Quantity must be at least 1.")
    if quantity > listing.quantity_remaining:
        raise ValueError(f"Only {listing.quantity_remaining} unit(s) remain in this listing.")

    gross_amount = _s12_money(Decimal(str(listing.unit_price)) * Decimal(str(quantity)))
    market_fee   = _s12_money(gross_amount * _S12_MARKET_FEE_RATE)
    seller_net   = _s12_money(gross_amount - market_fee)

    buyer_cash = _s12_money(buyer.cash)
    if buyer_cash < gross_amount:
        raise ValueError(
            f"Insufficient funds. Purchase costs {gross_amount} XGP, "
            f"you have {buyer_cash} XGP."
        )

    seller = db.query(Player).filter(Player.id == listing.seller_player_id).first()
    if seller is None:
        raise ValueError("Seller account not found.")

    buyer_before  = buyer_cash
    seller_before = _s12_money(seller.cash)

    buyer.cash  = buyer_before  - gross_amount
    seller.cash = seller_before + seller_net

    buyer_after  = _s12_money(buyer.cash)
    seller_after = _s12_money(seller.cash)

    listing.quantity_remaining -= quantity
    if listing.quantity_remaining <= 0:
        listing.quantity_remaining = 0
        listing.listing_status = "sold_out"

    item_label = listing.item_id or listing.basket_name

    trade = MarketTrade(
        listing_id=listing.id,
        seller_player_id=listing.seller_player_id,
        buyer_player_id=buyer.id,
        listing_type=listing.listing_type,
        item_id=item_label,
        quantity=quantity,
        unit_price_xgp=listing.unit_price,
        gross_amount_xgp=gross_amount,
        market_fee_xgp=market_fee,
        seller_net_xgp=seller_net,
        buyer_balance_before=buyer_before,
        buyer_balance_after=buyer_after,
        seller_balance_before=seller_before,
        seller_balance_after=seller_after,
        day_number=current_day,
    )
    db.add(trade)

    db.add(XGPTransaction(
        player_id=buyer.id,
        transaction_type="market_purchase",
        direction="out",
        amount=gross_amount,
        balance_before=buyer_before,
        balance_after=buyer_after,
        reference_type="market_listing",
        reference_id=str(listing.id),
        description=f"Step 12 purchase: {quantity}\u00d7 {item_label}",
    ))
    db.add(XGPTransaction(
        player_id=seller.id,
        transaction_type="market_sale",
        direction="in",
        amount=seller_net,
        balance_before=seller_before,
        balance_after=seller_after,
        reference_type="market_listing",
        reference_id=str(listing.id),
        description=f"Step 12 sale: {quantity}\u00d7 {item_label} (2% fee deducted)",
    ))
    db.add(ContributionEvent(
        player_id=buyer.id,
        event_type="market_trade",
        xgp_value=float(gross_amount),
        event_units=float(quantity),
    ))
    db.add(ContributionEvent(
        player_id=seller.id,
        event_type="market_trade",
        xgp_value=float(seller_net),
        event_units=float(quantity),
    ))

    seller.completed_trades_count   = (seller.completed_trades_count or 0) + 1
    seller.reputation               = (seller.reputation or 0) + 1
    seller.marketplace_rating_score = (seller.marketplace_rating_score or 0.0) + 1.0

    db.commit()
    db.refresh(trade)

    return {
        "message":             "Marketplace purchase completed.",
        "trade_id":            str(trade.id),
        "listing_id":          str(listing.id),
        "listing_type":        listing.listing_type,
        "item_id":             item_label,
        "quantity":            quantity,
        "unit_price_xgp":      float(listing.unit_price),
        "gross_amount_xgp":    float(gross_amount),
        "market_fee_xgp":      float(market_fee),
        "seller_net_xgp":      float(seller_net),
        "buyer_balance_after": float(buyer.cash),
        "listing_status":      listing.listing_status,
    }


def expire_s12_listings(db: Session, current_day_number: int) -> int:
    """Expire active Step 12 abstract listings whose expires_day has passed.

    Unlike Step 8.5 physical listings, NO goods are returned on expiration —
    the listing fee was already paid as a non-refundable anti-spam measure.

    Returns the count of listings that were expired.
    """
    stale = (
        db.query(MarketListing)
        .filter(
            MarketListing.listing_status == "active",
            MarketListing.listing_type.isnot(None),
            MarketListing.expires_day < current_day_number,
        )
        .all()
    )
    for lst in stale:
        lst.listing_status = "expired"
    if stale:
        db.commit()
    return len(stale)


def build_marketplace_summary(db: Session, player: Player) -> dict[str, Any]:
    """Return a player's Step 12 marketplace profile summary."""
    active_listings = (
        db.query(MarketListing)
        .filter(
            MarketListing.seller_player_id == player.id,
            MarketListing.listing_status == "active",
            MarketListing.listing_type.isnot(None),
        )
        .count()
    )
    trades_as_seller = (
        db.query(MarketTrade)
        .filter(MarketTrade.seller_player_id == player.id)
        .count()
    )
    trades_as_buyer = (
        db.query(MarketTrade)
        .filter(MarketTrade.buyer_player_id == player.id)
        .count()
    )
    return {
        "player_id":                str(player.id),
        "active_s12_listings":      active_listings,
        "completed_trades_count":   player.completed_trades_count or 0,
        "trades_as_seller":         trades_as_seller,
        "trades_as_buyer":          trades_as_buyer,
        "reputation":               player.reputation or 0,
        "marketplace_rating_score": float(player.marketplace_rating_score or 0.0),
    }


# ═══════════════════════════════════════════════════════════════════════════════

class MarketplaceEngine:
    """Processes all player marketplace actions for Gold Penny."""

    # ── Internal helpers ─────────────────────────────────────────────────────

    def _money(self, val: Any) -> Decimal:
        return Decimal(str(val)).quantize(_D("0.01"), rounding=ROUND_HALF_UP)

    def _get_current_day(self, db: Session) -> int:
        state = db.query(GameState).order_by(GameState.id.asc()).first()
        return int(state.current_day) if state else 1

    def _get_economy(self, db: Session) -> EconomyState | None:
        return db.query(EconomyState).order_by(EconomyState.day.desc()).first()

    def _get_basket_reference_price(self, basket_name: str, db: Session) -> Decimal:
        """Economy-adjusted reference price for guardrail computation.

        Applies inflation pressure above 5% so that guardrails track
        in-game price levels rather than being static.
        """
        base = _BASKET_BASE_PRICES.get(basket_name, _D("10.00"))
        economy = self._get_economy(db)
        if economy and economy.inflation_rate > 5.0:
            inflation_mod = _D(str(1.0 + (economy.inflation_rate - 5.0) * 0.01))
            base = self._money(base * inflation_mod)
        return base

    def _parse_uuid(self, value: str, label: str) -> _uuid_module.UUID:
        try:
            return _uuid_module.UUID(value)
        except (ValueError, AttributeError):
            raise ValueError(f"Invalid {label} format.")

    def _get_player_inventory_row(
        self, player_id: Any, basket_name: str, db: Session
    ) -> PlayerInventory | None:
        return (
            db.query(PlayerInventory)
            .filter(
                PlayerInventory.player_id == player_id,
                PlayerInventory.basket_name == basket_name,
            )
            .first()
        )

    def _get_business_inventory_row(
        self, business_id: Any, basket_name: str, db: Session
    ) -> BusinessInventory | None:
        return (
            db.query(BusinessInventory)
            .filter(
                BusinessInventory.business_id == business_id,
                BusinessInventory.basket_name == basket_name,
            )
            .first()
        )

    def _active_listing_count(self, player_id: Any, db: Session) -> int:
        return (
            db.query(MarketListing)
            .filter(
                MarketListing.seller_player_id == player_id,
                MarketListing.listing_status == "active",
            )
            .count()
        )

    # ── Suspicious pattern detection ─────────────────────────────────────────

    def _check_suspicious_patterns(
        self,
        listing: MarketListing,
        buyer: Player,
        current_day: int,
        db: Session,
    ) -> tuple[bool, str]:
        """Detect suspicious trading signals and return (flag, notes).

        Patterns checked:
        - Repeated seller-buyer pair trades in a single in-game day.
        - Unit price within 5% of the allowed floor (near-minimum laundering).
        - Unit price within 5% of the allowed ceiling (near-maximum laundering).

        No automated action is taken in Step 8.5. Records are flagged for
        future anti-cheat review.
        """
        flags: list[str] = []

        # Repeated same-pair trades today
        pair_count = (
            db.query(MarketTransaction)
            .filter(
                MarketTransaction.seller_player_id == listing.seller_player_id,
                MarketTransaction.buyer_player_id == buyer.id,
                MarketTransaction.created_day == current_day,
            )
            .count()
        )
        if pair_count >= _SUSPICIOUS_PAIR_THRESHOLD:
            flags.append(f"repeat_pair:{pair_count}_trades_today")

        # Near guardrail pricing
        ref_price = self._get_basket_reference_price(listing.basket_name, db)
        min_guard = self._money(ref_price * _MIN_PRICE_FACTOR)
        max_guard = self._money(ref_price * _MAX_PRICE_FACTOR)
        unit_price = self._money(listing.unit_price)

        if unit_price <= self._money(min_guard * _D("1.05")):
            flags.append("price_near_floor")
        if unit_price >= self._money(max_guard * _D("0.95")):
            flags.append("price_near_ceiling")

        if flags:
            return True, ";".join(flags)
        return False, ""

    # ── Serializers ──────────────────────────────────────────────────────────

    def _serialize_listing(self, listing: MarketListing) -> dict[str, Any]:
        return {
            "listing_id": str(listing.id),
            "seller_player_id": str(listing.seller_player_id),
            "source_type": listing.source_type,
            "basket_name": listing.basket_name,
            "quantity_total": listing.quantity_total,
            "quantity_remaining": listing.quantity_remaining,
            "unit_price": float(listing.unit_price),
            "listing_status": listing.listing_status,
            "region": listing.region,
            "created_day": listing.created_day,
            "expires_day": listing.expires_day,
        }

    def _serialize_transaction(self, tx: MarketTransaction) -> dict[str, Any]:
        return {
            "transaction_id": str(tx.id),
            "listing_id": str(tx.listing_id),
            "seller_player_id": str(tx.seller_player_id),
            "buyer_player_id": str(tx.buyer_player_id),
            "basket_name": tx.basket_name,
            "quantity": tx.quantity,
            "unit_price": float(tx.unit_price),
            "gross_total": float(tx.gross_total),
            "marketplace_fee": float(tx.marketplace_fee),
            "seller_net": float(tx.seller_net),
            "buyer_region": tx.buyer_region,
            "seller_region": tx.seller_region,
            "created_day": tx.created_day,
        }

    # ── Return-to-source helper ───────────────────────────────────────────────

    def _return_to_source(
        self, listing: MarketListing, quantity: int, db: Session
    ) -> None:
        """Return unsold goods to the original inventory source.

        Used by both cancel and expire flows. Does not commit — caller is
        responsible for the final db.commit().
        """
        if listing.source_type == "player_inventory":
            inv = self._get_player_inventory_row(
                listing.seller_player_id, listing.basket_name, db
            )
            if inv is not None:
                inv.quantity += quantity
            else:
                db.add(
                    PlayerInventory(
                        player_id=listing.seller_player_id,
                        basket_name=listing.basket_name,
                        quantity=quantity,
                    )
                )
        elif listing.source_type == "business_inventory" and listing.source_business_id:
            inv = self._get_business_inventory_row(
                listing.source_business_id, listing.basket_name, db
            )
            if inv is not None:
                inv.quantity += quantity
            else:
                db.add(
                    BusinessInventory(
                        business_id=listing.source_business_id,
                        basket_name=listing.basket_name,
                        quantity=quantity,
                    )
                )

    # ── EXPIRE OLD LISTINGS ──────────────────────────────────────────────────

    def expire_old_listings(self, current_day: int, db: Session) -> int:
        """Expire active listings whose expires_day has passed.

        Returns quantity_remaining to the original inventory source,
        marks listing_status = 'expired', and returns the count expired.

        This is called automatically at the start of browse and buy flows.
        """
        stale = (
            db.query(MarketListing)
            .filter(
                MarketListing.listing_status == "active",
                MarketListing.expires_day < current_day,
            )
            .all()
        )
        count = 0
        for listing in stale:
            if listing.quantity_remaining > 0:
                self._return_to_source(listing, listing.quantity_remaining, db)
            listing.listing_status = "expired"
            count += 1
        if count:
            db.commit()
        return count

    # ── CREATE LISTING ───────────────────────────────────────────────────────

    def create_market_listing(
        self,
        player: Player,
        source_type: str,
        basket_name: str,
        quantity: int,
        unit_price: float,
        current_day: int,
        db: Session,
        source_business_id: str | None = None,
    ) -> dict[str, Any]:
        """Create a marketplace listing from real player or business inventory.

        Inventory is removed from the source immediately so it cannot be
        double-spent. Any validation failure raises ValueError.
        """
        # ── Basket approval ──────────────────────────────────────────────────
        if basket_name not in _APPROVED_BASKETS:
            raise ValueError(
                f"'{basket_name}' is not approved for listing. "
                f"Approved baskets: {sorted(_APPROVED_BASKETS)}"
            )

        # ── Quantity bounds ──────────────────────────────────────────────────
        if quantity <= 0:
            raise ValueError("Quantity must be at least 1.")
        if quantity > _MAX_QUANTITY_PER_LISTING:
            raise ValueError(
                f"Maximum quantity per listing is {_MAX_QUANTITY_PER_LISTING}."
            )

        # ── Price guardrails ─────────────────────────────────────────────────
        unit_price_d = self._money(unit_price)
        if unit_price_d <= _D("0"):
            raise ValueError("Unit price must be greater than zero.")

        ref_price = self._get_basket_reference_price(basket_name, db)
        min_price = self._money(ref_price * _MIN_PRICE_FACTOR)
        max_price = self._money(ref_price * _MAX_PRICE_FACTOR)

        if unit_price_d < min_price:
            raise ValueError(
                f"Unit price ${unit_price_d} is below the minimum "
                f"${min_price} (70% of market reference ${ref_price})."
            )
        if unit_price_d > max_price:
            raise ValueError(
                f"Unit price ${unit_price_d} exceeds the maximum "
                f"${max_price} (180% of market reference ${ref_price})."
            )

        # ── Source type ──────────────────────────────────────────────────────
        if source_type not in ("player_inventory", "business_inventory"):
            raise ValueError(
                "source_type must be 'player_inventory' or 'business_inventory'."
            )

        # ── Active listing cap ───────────────────────────────────────────────
        active_count = self._active_listing_count(player.id, db)
        if active_count >= _MAX_ACTIVE_LISTINGS_PER_PLAYER:
            raise ValueError(
                f"You already have {active_count} active listings. "
                f"Maximum is {_MAX_ACTIVE_LISTINGS_PER_PLAYER}. "
                "Cancel or wait for listings to sell before adding more."
            )

        # ── Reserve inventory from source ────────────────────────────────────
        biz_uuid: _uuid_module.UUID | None = None

        if source_type == "player_inventory":
            inv = self._get_player_inventory_row(player.id, basket_name, db)
            available = inv.quantity if inv else 0
            if available < quantity:
                raise ValueError(
                    f"Insufficient player inventory. "
                    f"You have {available} × {basket_name}, need {quantity}."
                )
            inv.quantity -= quantity  # type: ignore[union-attr]

        else:  # business_inventory
            if source_business_id is None:
                raise ValueError(
                    "source_business_id is required when source_type is 'business_inventory'."
                )
            biz_uuid = self._parse_uuid(source_business_id, "source_business_id")
            business = (
                db.query(Business)
                .filter(
                    Business.id == biz_uuid,
                    Business.player_id == player.id,
                )
                .first()
            )
            if business is None:
                raise ValueError("Business not found or does not belong to you.")
            if business.status != "active":
                raise ValueError("Only active businesses can list inventory.")

            inv = self._get_business_inventory_row(biz_uuid, basket_name, db)
            available = inv.quantity if inv else 0
            if available < quantity:
                raise ValueError(
                    f"Insufficient business inventory. "
                    f"Business has {available} × {basket_name}, need {quantity}."
                )
            inv.quantity -= quantity  # type: ignore[union-attr]

        # ── Create listing ───────────────────────────────────────────────────
        expires_day = current_day + _DEFAULT_LISTING_DAYS
        listing = MarketListing(
            seller_player_id=player.id,
            source_type=source_type,
            source_business_id=biz_uuid,
            basket_name=basket_name,
            quantity_total=quantity,
            quantity_remaining=quantity,
            unit_price=unit_price_d,
            listing_status="active",
            region=getattr(player, "region", "suburban") or "suburban",
            created_day=current_day,
            expires_day=expires_day,
        )
        db.add(listing)
        db.commit()
        db.refresh(listing)

        return {
            "message": "Listing created.",
            "listing_id": str(listing.id),
            "basket_name": basket_name,
            "quantity_total": quantity,
            "unit_price": float(unit_price_d),
            "min_price_allowed": float(min_price),
            "max_price_allowed": float(max_price),
            "listing_status": "active",
            "expires_day": expires_day,
            "source_type": source_type,
        }

    # ── BROWSE LISTINGS ──────────────────────────────────────────────────────

    def browse_listings(
        self,
        db: Session,
        basket_name: str | None = None,
        region: str | None = None,
        min_price: float | None = None,
        max_price: float | None = None,
        current_day: int | None = None,
    ) -> list[dict[str, Any]]:
        """Return active listings with optional filters.

        Runs expiration check before querying so buyers never see stale listings.
        Results ordered by unit_price ascending (cheapest first).
        """
        if current_day is not None:
            self.expire_old_listings(current_day, db)

        q = db.query(MarketListing).filter(MarketListing.listing_status == "active")

        if basket_name:
            q = q.filter(MarketListing.basket_name == basket_name)
        if region:
            q = q.filter(MarketListing.region == region)
        if min_price is not None:
            q = q.filter(MarketListing.unit_price >= self._money(min_price))
        if max_price is not None:
            q = q.filter(MarketListing.unit_price <= self._money(max_price))

        listings = q.order_by(MarketListing.unit_price.asc()).all()
        return [self._serialize_listing(lst) for lst in listings]

    # ── PURCHASE LISTING ─────────────────────────────────────────────────────

    def purchase_market_listing(
        self,
        buyer: Player,
        listing_id: str,
        quantity: int,
        current_day: int,
        db: Session,
    ) -> dict[str, Any]:
        """Execute a marketplace purchase.

        Flow:
        1. Expire stale listings.
        2. Validate listing, quantity, buyer.
        3. Compute gross_total, fee (5%), seller_net.
        4. Verify buyer cash.
        5. Deduct buyer cash; credit seller net.
        6. Add goods to buyer PlayerInventory.
        7. Decrement listing quantity_remaining; mark sold_out if empty.
        8. Detect suspicious patterns; log.
        9. Create MarketTransaction and MarketFeeLog.
        10. Return summary.

        Any validation failure raises ValueError (mapped to HTTP 400 by caller).
        """
        self.expire_old_listings(current_day, db)

        listing_uuid = self._parse_uuid(listing_id, "listing_id")
        listing = db.query(MarketListing).filter(MarketListing.id == listing_uuid).first()
        if listing is None:
            raise ValueError("Listing not found.")

        if listing.listing_status != "active":
            raise ValueError(
                f"Listing is not active (status: '{listing.listing_status}')."
            )

        # Self-buy prevention (unconditional, non-bypassable)
        if str(listing.seller_player_id) == str(buyer.id):
            raise ValueError("You cannot purchase your own listing.")

        # Quantity validation
        if quantity <= 0:
            raise ValueError("Quantity must be at least 1.")
        if quantity > listing.quantity_remaining:
            raise ValueError(
                f"Only {listing.quantity_remaining} unit(s) remain in this listing."
            )

        # Financial computation
        gross_total = self._money(Decimal(str(listing.unit_price)) * quantity)
        marketplace_fee = self._money(gross_total * _MARKETPLACE_FEE_RATE)
        seller_net = self._money(gross_total - marketplace_fee)

        # Buyer cash check
        buyer_cash = self._money(buyer.cash)
        if buyer_cash < gross_total:
            raise ValueError(
                f"Insufficient funds. Purchase costs ${gross_total}, "
                f"you have ${buyer_cash}."
            )

        # Load seller (must exist)
        seller = db.query(Player).filter(Player.id == listing.seller_player_id).first()
        if seller is None:
            raise ValueError("Seller account not found. Purchase cannot be completed.")

        # ── Cash transfer ─────────────────────────────────────────────────────
        buyer.cash = self._money(buyer.cash) - gross_total
        seller.cash = self._money(seller.cash) + seller_net
        # The marketplace_fee is sunk — not credited to any account.

        # ── Goods transfer to buyer ───────────────────────────────────────────
        buyer_inv = self._get_player_inventory_row(buyer.id, listing.basket_name, db)
        if buyer_inv is not None:
            buyer_inv.quantity += quantity
        else:
            db.add(
                PlayerInventory(
                    player_id=buyer.id,
                    basket_name=listing.basket_name,
                    quantity=quantity,
                    created_day=current_day,
                )
            )

        # ── Update listing ───────────────────────────────────────────────────
        listing.quantity_remaining -= quantity
        if listing.quantity_remaining == 0:
            listing.listing_status = "sold_out"

        # ── Suspicious pattern detection ─────────────────────────────────────
        susp_flag, susp_notes = self._check_suspicious_patterns(
            listing, buyer, current_day, db
        )

        # ── Create transaction record ─────────────────────────────────────────
        seller_region = getattr(seller, "region", "suburban") or "suburban"
        buyer_region = getattr(buyer, "region", "suburban") or "suburban"

        tx = MarketTransaction(
            listing_id=listing.id,
            seller_player_id=listing.seller_player_id,
            buyer_player_id=buyer.id,
            source_type=listing.source_type,
            basket_name=listing.basket_name,
            quantity=quantity,
            unit_price=listing.unit_price,
            gross_total=gross_total,
            marketplace_fee=marketplace_fee,
            seller_net=seller_net,
            buyer_region=buyer_region,
            seller_region=seller_region,
            created_day=current_day,
            suspicious_flag=susp_flag,
            suspicious_notes=susp_notes if susp_notes else None,
        )
        db.add(tx)
        db.flush()  # assign tx.id before creating the fee log

        # ── Create fee log ────────────────────────────────────────────────────
        fee_log = MarketFeeLog(
            transaction_id=tx.id,
            listing_id=listing.id,
            fee_amount=marketplace_fee,
            fee_rate=float(_MARKETPLACE_FEE_RATE),
            fee_type="marketplace_transaction_fee",
            created_day=current_day,
        )
        db.add(fee_log)
        db.commit()

        return {
            "message": "Marketplace purchase completed.",
            "listing_id": str(listing.id),
            "basket_name": listing.basket_name,
            "quantity": quantity,
            "unit_price": float(listing.unit_price),
            "gross_total": float(gross_total),
            "marketplace_fee": float(marketplace_fee),
            "seller_net": float(seller_net),
            "buyer_cash_remaining": float(buyer.cash),
            "listing_status": listing.listing_status,
        }

    # ── CANCEL LISTING ───────────────────────────────────────────────────────

    def cancel_market_listing(
        self,
        player: Player,
        listing_id: str,
        db: Session,
    ) -> dict[str, Any]:
        """Cancel a player's own active listing and return unsold goods.

        Validates ownership and status, returns quantity_remaining to the
        original inventory source, and marks the listing cancelled.
        """
        listing_uuid = self._parse_uuid(listing_id, "listing_id")
        listing = db.query(MarketListing).filter(MarketListing.id == listing_uuid).first()
        if listing is None:
            raise ValueError("Listing not found.")

        if str(listing.seller_player_id) != str(player.id):
            raise ValueError("This listing does not belong to you.")

        if listing.listing_status != "active":
            raise ValueError(
                f"Cannot cancel listing with status '{listing.listing_status}'. "
                "Only active listings can be cancelled."
            )

        # Capture quantity before returning (response must show what was returned)
        returned_qty = listing.quantity_remaining

        if returned_qty > 0:
            self._return_to_source(listing, returned_qty, db)

        listing.listing_status = "cancelled"
        db.commit()

        return {
            "message": "Listing cancelled. Unsold goods returned to inventory.",
            "listing_id": str(listing.id),
            "basket_name": listing.basket_name,
            "quantity_returned": returned_qty,
            "return_destination": listing.source_type,
            "listing_status": "cancelled",
        }

    # ── MY LISTINGS ──────────────────────────────────────────────────────────

    def get_my_listings(self, player: Player, db: Session) -> list[dict[str, Any]]:
        """Return all marketplace listings for the authenticated player."""
        listings = (
            db.query(MarketListing)
            .filter(MarketListing.seller_player_id == player.id)
            .order_by(MarketListing.created_day.desc())
            .all()
        )
        return [self._serialize_listing(lst) for lst in listings]

    # ── MY TRANSACTIONS ──────────────────────────────────────────────────────

    def get_my_transactions(self, player: Player, db: Session) -> list[dict[str, Any]]:
        """Return all buy and sell transactions for the authenticated player.

        Each record includes a 'role' field: 'buyer' or 'seller'.
        Ordered newest first.
        """
        txs = (
            db.query(MarketTransaction)
            .filter(
                or_(
                    MarketTransaction.buyer_player_id == player.id,
                    MarketTransaction.seller_player_id == player.id,
                )
            )
            .order_by(MarketTransaction.created_at.desc())
            .all()
        )
        result = []
        for tx in txs:
            row = self._serialize_transaction(tx)
            row["role"] = "buyer" if str(tx.buyer_player_id) == str(player.id) else "seller"
            result.append(row)
        return result

    # ── FEE LOGS ─────────────────────────────────────────────────────────────

    def get_fee_logs(self, db: Session, limit: int = 50) -> list[dict[str, Any]]:
        """Return recent marketplace fee logs for economy balancing and debugging."""
        logs = (
            db.query(MarketFeeLog)
            .order_by(MarketFeeLog.created_at.desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "fee_log_id": str(log.id),
                "transaction_id": str(log.transaction_id),
                "listing_id": str(log.listing_id),
                "fee_amount": float(log.fee_amount),
                "fee_rate": log.fee_rate,
                "fee_type": log.fee_type,
                "created_day": log.created_day,
            }
            for log in logs
        ]

    # ── PLAYER INVENTORY QUERY ───────────────────────────────────────────────

    def get_player_inventory(self, player: Player, db: Session) -> list[dict[str, Any]]:
        """Return the player's current household basket goods inventory."""
        rows = (
            db.query(PlayerInventory)
            .filter(PlayerInventory.player_id == player.id)
            .all()
        )
        return [
            {
                "basket_name": row.basket_name,
                "quantity": row.quantity,
                "created_day": row.created_day,
            }
            for row in rows
            if row.quantity > 0
        ]
