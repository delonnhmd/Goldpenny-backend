"""Cost circuit breaker for real-world event generation."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Callable

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.realworld_generation_cost import (
    CostBreakerAlert,
    RealWorldGenerationCost,
)

logger = logging.getLogger(__name__)


OPERATIONAL_TARGET = 0.10
HARD_BREAKER_THRESHOLD = 0.20
_DEFAULT_MAU_STUB = 100


class CostBreaker:
    """Tracks generation spend and blocks costly real-world generation."""

    def __init__(
        self,
        db: Session,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.db = db
        self._clock = clock if clock is not None else (lambda: datetime.now(timezone.utc))

    def record_generation_cost(self, event_id: str, cost_usd: float) -> RealWorldGenerationCost:
        """Append a per-event generation cost row."""
        row = RealWorldGenerationCost(
            event_id=event_id,
            cost_usd=Decimal(str(cost_usd)),
            recorded_at=self._clock(),
        )
        self.db.add(row)
        self.db.flush()
        return row

    def monthly_cost_per_mau(self) -> float:
        """Return recorded last-30-day generation cost divided by MAU."""
        since = self._clock() - timedelta(days=30)
        total = (
            self.db.query(func.coalesce(func.sum(RealWorldGenerationCost.cost_usd), 0))
            .filter(RealWorldGenerationCost.recorded_at >= since)
            .scalar()
        )
        mau = max(1, self._current_mau())
        return float(total or 0) / mau

    def is_tripped(self) -> bool:
        """Return True when cost per MAU is above the hard breaker threshold."""
        return self.monthly_cost_per_mau() > HARD_BREAKER_THRESHOLD

    def notify_operator(self, reason: str) -> CostBreakerAlert:
        """Log and persist an operator alert. Email delivery is Phase 3-B-2."""
        monthly_cost = self.monthly_cost_per_mau()
        logger.error("realworld_cost_breaker_tripped: %s", reason)
        row = CostBreakerAlert(
            reason=reason,
            monthly_cost_per_mau=Decimal(str(monthly_cost)),
            threshold_usd=Decimal(str(HARD_BREAKER_THRESHOLD)),
        )
        self.db.add(row)
        self.db.flush()
        return row

    def _current_mau(self) -> int:
        # TODO(Phase 3-B-2): replace with real analytics MAU once backend exposure exists.
        return _DEFAULT_MAU_STUB
