import os
import unittest
import uuid
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_stock_trading_service.db")

from app.db.database import Base
from app.models.enums import TradeSide
from app.models.player import Player
from app.models.player_stock_holding import PlayerStockHolding
from app.models.stock_daily_price import StockDailyPrice
from app.models.stock_trade_log import StockTradeLog
from app.models.user import User
from app.services.stock_trading_service import StockTradingService, ValidationError


class StockTradingServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:", future=True)
        self.SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=self.engine,
            future=True,
        )

        Base.metadata.create_all(
            bind=self.engine,
            tables=[
                User.__table__,
                Player.__table__,
                PlayerStockHolding.__table__,
                StockDailyPrice.__table__,
                StockTradeLog.__table__,
            ],
        )

        self.db = self.SessionLocal()
        self.service = StockTradingService()

        user = User(
            email=f"player-{uuid.uuid4()}@example.com",
            hashed_password="hashed-password",
        )
        self.db.add(user)
        self.db.flush()

        player = Player(user_id=user.id, cash=Decimal("1000.00"))
        self.db.add(player)
        self.db.commit()
        self.db.refresh(player)
        self.player = player

        self._seed_price(day=1, ticker="GPEN", close_price=Decimal("10.0000"))

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def _seed_price(self, day: int, ticker: str, close_price: Decimal) -> None:
        row = StockDailyPrice(
            day=day,
            ticker=ticker,
            sector="tech",
            open_price=close_price,
            close_price=close_price,
            daily_change_pct=Decimal("0.0000"),
            macro_impact=Decimal("0.0000"),
            noise_component=Decimal("0.0000"),
        )
        self.db.add(row)
        self.db.commit()

    def _holding(self, ticker: str) -> PlayerStockHolding | None:
        return (
            self.db.query(PlayerStockHolding)
            .filter(
                PlayerStockHolding.player_id == self.player.id,
                PlayerStockHolding.stock_id == ticker,
            )
            .first()
        )

    def test_buy_successful(self) -> None:
        result = self.service.buy_stock(self.db, str(self.player.id), "GPEN", 10)

        self.assertEqual(result["shares_bought"], 10)
        self.assertAlmostEqual(result["execution_price"], 10.00, places=2)
        self.assertAlmostEqual(result["gross_amount"], 100.00, places=2)
        self.assertAlmostEqual(result["fee_amount"], 0.30, places=2)
        self.assertAlmostEqual(result["total_cost"], 100.30, places=2)
        self.assertAlmostEqual(result["remaining_cash"], 899.70, places=2)
        self.assertEqual(result["updated_holding_shares"], 10)

        holding = self._holding("GPEN")
        self.assertIsNotNone(holding)
        self.assertEqual(int(holding.shares_owned), 10)
        self.assertEqual(Decimal(str(holding.average_cost_basis)), Decimal("10.0000"))

    def test_buy_rejected_for_insufficient_cash(self) -> None:
        self.player.cash_xgp = Decimal("5.00")
        self.db.add(self.player)
        self.db.commit()

        with self.assertRaises(ValidationError):
            self.service.buy_stock(self.db, str(self.player.id), "GPEN", 1)

        trades = self.db.query(StockTradeLog).all()
        self.assertEqual(len(trades), 0)
        self.assertIsNone(self._holding("GPEN"))

    def test_sell_successful(self) -> None:
        self.service.buy_stock(self.db, str(self.player.id), "GPEN", 10)
        self._seed_price(day=2, ticker="GPEN", close_price=Decimal("12.0000"))

        result = self.service.sell_stock(self.db, str(self.player.id), "GPEN", 4)

        self.assertEqual(result["shares_sold"], 4)
        self.assertAlmostEqual(result["gross_amount"], 48.00, places=2)
        self.assertAlmostEqual(result["fee_amount"], 0.14, places=2)
        self.assertAlmostEqual(result["net_amount"], 47.86, places=2)
        self.assertAlmostEqual(result["remaining_cash"], 947.56, places=2)
        self.assertEqual(result["remaining_holding_shares"], 6)

        sell_trade = (
            self.db.query(StockTradeLog)
            .filter(StockTradeLog.side == TradeSide.sell)
            .first()
        )
        self.assertIsNotNone(sell_trade)

    def test_sell_rejected_for_insufficient_shares(self) -> None:
        self.service.buy_stock(self.db, str(self.player.id), "GPEN", 2)
        self._seed_price(day=2, ticker="GPEN", close_price=Decimal("12.0000"))

        with self.assertRaises(ValidationError):
            self.service.sell_stock(self.db, str(self.player.id), "GPEN", 3)

    def test_full_sell_deletes_holding_row(self) -> None:
        self.service.buy_stock(self.db, str(self.player.id), "GPEN", 2)
        self._seed_price(day=2, ticker="GPEN", close_price=Decimal("12.0000"))

        result = self.service.sell_stock(self.db, str(self.player.id), "GPEN", 2)
        holding = self._holding("GPEN")

        self.assertEqual(result["remaining_holding_shares"], 0)
        self.assertIsNone(holding)

    def test_weighted_average_cost_basis_after_multiple_buys(self) -> None:
        self.service.buy_stock(self.db, str(self.player.id), "GPEN", 10)
        self._seed_price(day=2, ticker="GPEN", close_price=Decimal("20.0000"))

        result = self.service.buy_stock(self.db, str(self.player.id), "GPEN", 10)
        holding = self._holding("GPEN")

        self.assertIsNotNone(holding)
        self.assertEqual(int(holding.shares_owned), 20)
        self.assertAlmostEqual(result["updated_average_cost_basis"], 15.00, places=2)
        self.assertEqual(Decimal(str(holding.average_cost_basis)), Decimal("15.0000"))

    def test_realized_pnl_after_sell(self) -> None:
        self.service.buy_stock(self.db, str(self.player.id), "GPEN", 10)
        self._seed_price(day=2, ticker="GPEN", close_price=Decimal("12.0000"))

        result = self.service.sell_stock(self.db, str(self.player.id), "GPEN", 4)

        self.assertAlmostEqual(result["realized_pnl"], 7.86, places=2)

    def test_get_latest_quote_shape(self) -> None:
        quote = self.service.get_latest_quote(self.db, "GPEN")
        self.assertSetEqual(
            set(quote.keys()),
            {"ticker", "sector", "latest_day", "close_price", "daily_change_pct"},
        )


if __name__ == "__main__":
    unittest.main()
