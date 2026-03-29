from __future__ import annotations

import random
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.day_log import DayLog
from app.models.game_state import GameState
from app.models.job_action import JobAction
from app.models.player import Player


class DayEngine:
    FATIGUE_RECOVERY = 12.0
    STRESS_RECOVERY = 10
    HEALTH_RECOVERY = 3

    FATIGUE_HEALTH_PENALTY_THRESHOLD = 80.0
    STRESS_HEALTH_PENALTY_THRESHOLD = 90
    HEALTH_PENALTY_PER_RULE = 2

    def get_or_create_game_state(self, db: Session) -> GameState:
        state = db.query(GameState).order_by(GameState.id.asc()).first()
        if state is not None:
            return state

        state = GameState(
            current_day=1,
            real_world_timestamp=datetime.now(timezone.utc),
            economy_seed=self._generate_seed(),
        )
        db.add(state)
        db.commit()
        db.refresh(state)
        return state

    def end_player_day(self, db: Session, player: Player) -> dict[str, Any]:
        state = self.get_or_create_game_state(db)
        current_day = int(state.current_day)

        already_settled = (
            db.query(DayLog.id)
            .filter(DayLog.player_id == player.id, DayLog.day == current_day)
            .first()
        )
        if already_settled is not None:
            raise ValueError("Day already completed for the current in-game day.")

        starting_cash = self._money(player.cash)
        starting_health = int(player.health)
        starting_stress = int(player.stress)
        starting_fatigue = float(player.fatigue)
        hours_worked = int(player.total_hours_worked_today)
        actions_taken = int(player.work_actions_today)

        income_earned_raw = (
            db.query(func.coalesce(func.sum(JobAction.earned_cash), 0))
            .filter(JobAction.player_id == player.id, JobAction.day == current_day)
            .scalar()
        )
        income_earned = self._money(income_earned_raw)

        fatigue_after = max(starting_fatigue - self.FATIGUE_RECOVERY, 0.0)
        fatigue_recovered = round(starting_fatigue - fatigue_after, 2)
        player.fatigue = round(fatigue_after, 2)

        stress_after = max(starting_stress - self.STRESS_RECOVERY, 0)
        stress_recovered = starting_stress - stress_after
        player.stress = stress_after

        recovered_health = min(starting_health + self.HEALTH_RECOVERY, 100)
        health_recovered = recovered_health - starting_health
        player.health = recovered_health

        health_penalty = 0
        penalty_notes: list[str] = []

        if float(player.fatigue) > self.FATIGUE_HEALTH_PENALTY_THRESHOLD:
            player.health -= self.HEALTH_PENALTY_PER_RULE
            health_penalty += self.HEALTH_PENALTY_PER_RULE
            penalty_notes.append("fatigue_penalty_applied")

        if int(player.stress) > self.STRESS_HEALTH_PENALTY_THRESHOLD:
            player.health -= self.HEALTH_PENALTY_PER_RULE
            health_penalty += self.HEALTH_PENALTY_PER_RULE
            penalty_notes.append("stress_penalty_applied")

        player.health = int(self._clamp(float(player.health), 0.0, 100.0))

        player.hours_available = 16
        player.main_job_hours_today = 0
        player.side_job_hours_today = 0
        player.total_hours_worked_today = 0
        player.work_actions_today = 0

        ending_cash = self._money(player.cash)
        ending_health = int(player.health)
        ending_stress = int(player.stress)
        ending_fatigue = float(player.fatigue)

        notes = "; ".join(penalty_notes) if penalty_notes else None

        log = DayLog(
            player_id=player.id,
            day=current_day,
            starting_cash=starting_cash,
            ending_cash=ending_cash,
            starting_health=starting_health,
            ending_health=ending_health,
            starting_stress=starting_stress,
            ending_stress=ending_stress,
            starting_fatigue=starting_fatigue,
            ending_fatigue=ending_fatigue,
            hours_worked=hours_worked,
            income_earned=income_earned,
            actions_taken=actions_taken,
            notes=notes,
        )

        state.current_day = current_day + 1
        state.real_world_timestamp = datetime.now(timezone.utc)

        db.add(log)
        db.commit()
        db.refresh(player)

        return {
            "message": "Day completed",
            "day": current_day,
            "fatigue_recovered": fatigue_recovered,
            "stress_recovered": stress_recovered,
            "health_recovered": health_recovered,
            "health_penalty": health_penalty,
            "next_day_hours_available": int(player.hours_available),
            "updated_player": {
                "cash": float(player.cash),
                "health": int(player.health),
                "stress": int(player.stress),
                "fatigue": float(player.fatigue),
            },
        }

    @staticmethod
    def _money(value: Decimal | float | int | str) -> Decimal:
        amount = value if isinstance(value, Decimal) else Decimal(str(value))
        return amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    @staticmethod
    def _clamp(value: float, minimum: float, maximum: float) -> float:
        return max(minimum, min(maximum, value))

    @staticmethod
    def _generate_seed() -> int:
        return random.SystemRandom().randint(1, 2_147_483_647)
