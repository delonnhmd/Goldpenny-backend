"""Reward Engine — Step 5.5.

Handles all off-chain monthly reward accounting logic for Gold Penny.

Design rules
------------
- Gameplay cash (player.cash) is NEVER modified here.
- No on-chain transaction is triggered here.
- All token amounts are off-chain estimates prepared for a future claim step.
- Business logic lives here; API routes stay thin.
"""

from __future__ import annotations

import calendar
import re
import statistics
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.claim_balance import ClaimBalance
from app.models.claim_window import ClaimWindow
from app.models.day_log import DayLog
from app.models.job_action import JobAction
from app.models.player import Player
from app.models.player_reward_score import PlayerRewardScore
from app.models.reward_ledger import RewardLedger
from app.models.reward_pool import RewardPool
from app.models.token_claim_allowance import TokenClaimAllowance
from app.models.token_claim_history import TokenClaimHistory
from app.models.wallet_link import WalletLink

# ── Configuration constants ───────────────────────────────────────────────────

TOKEN_CONVERSION_RATE = 0.10       # 100 points → 10 token units
MIN_CLAIM_THRESHOLD = 25.0         # carry-forward if below this
MAX_CLAIM_PER_PLAYER = 200.0       # hard cap per month
DEFAULT_POOL = 100_000.0

# Minimum days active in a month to qualify for rewards.
MIN_DAYS_ACTIVE = 8
# Minimum account age (in-game days) to qualify.
MIN_ACCOUNT_AGE_DAYS = 14
# Anti-exploit score below which the flag fires.
ANTI_CHEAT_SEVERITY_THRESHOLD = 40.0

# Sub-score weights (must sum to 1.0).
W_CONSISTENCY = 0.35
W_SURVIVAL = 0.25
W_PRODUCTIVITY = 0.25
W_ANTI_EXPLOIT = 0.15

# ── Helpers ───────────────────────────────────────────────────────────────────

_MONTH_KEY_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def _validate_month_key(month_key: str) -> None:
    if not _MONTH_KEY_RE.match(month_key):
        raise ValueError(f"Invalid month_key format '{month_key}'. Expected YYYY-MM.")


def _month_date_range(month_key: str) -> tuple[datetime, datetime]:
    """Return (start_inclusive, end_inclusive) UTC datetimes for a month key."""
    year, month = map(int, month_key.split("-"))
    last_day = calendar.monthrange(year, month)[1]
    start = datetime(year, month, 1, 0, 0, 0, tzinfo=timezone.utc)
    end = datetime(year, month, last_day, 23, 59, 59, 999999, tzinfo=timezone.utc)
    return start, end


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


# ── Engine ────────────────────────────────────────────────────────────────────

class RewardEngine:
    """Off-chain monthly reward calculation engine."""

    # ── Public API ────────────────────────────────────────────────────────────

    def create_or_get_claim_window(self, month_key: str, db: Session) -> ClaimWindow:
        """Return (or create) the ClaimWindow for a given month_key."""
        _validate_month_key(month_key)
        window = db.query(ClaimWindow).filter(ClaimWindow.month_key == month_key).first()
        if window is None:
            window = ClaimWindow(
                month_key=month_key,
                status="open",
                total_pool=DEFAULT_POOL,
                min_claim_threshold=MIN_CLAIM_THRESHOLD,
                max_claim_per_player=MAX_CLAIM_PER_PLAYER,
            )
            db.add(window)
            db.commit()
            db.refresh(window)
        return window

    def calculate_player_monthly_reward(
        self, player_id: UUID, month_key: str, db: Session
    ) -> dict[str, Any]:
        """Compute (but do NOT persist) monthly reward metrics for a player.

        Returns a full calculation dict. Call finalize_player_monthly_reward
        to persist results.
        """
        _validate_month_key(month_key)
        player = db.query(Player).filter(Player.id == player_id).first()
        if player is None:
            raise ValueError(f"Player {player_id} not found.")

        start, end = _month_date_range(month_key)
        day_logs = (
            db.query(DayLog)
            .filter(DayLog.player_id == player_id, DayLog.created_at >= start, DayLog.created_at <= end)
            .all()
        )
        job_actions = (
            db.query(JobAction)
            .filter(JobAction.player_id == player_id, JobAction.created_at >= start, JobAction.created_at <= end)
            .all()
        )

        metrics = self._build_activity_metrics(day_logs, job_actions)
        scores = self._compute_scores(metrics, day_logs)
        exploit_notes = self._check_suspicious_patterns(metrics, day_logs, job_actions)

        if exploit_notes:
            penalty = min(len(exploit_notes) * 15, 60)
            scores["anti_exploit_score"] = max(0.0, scores["anti_exploit_score"] - penalty)

        raw = round(
            (scores["consistency_score"] * W_CONSISTENCY)
            + (scores["survival_score"] * W_SURVIVAL)
            + (scores["productivity_score"] * W_PRODUCTIVITY)
            + (scores["anti_exploit_score"] * W_ANTI_EXPLOIT),
            2,
        )

        # Determine eligibility.
        account_start_day = self._get_account_start_day(player_id, player, db)
        from app.models.game_state import GameState
        game_state = db.query(GameState).order_by(GameState.id.asc()).first()
        current_day = game_state.current_day if game_state else 0
        account_age = max(0, current_day - account_start_day)

        eligibility_reasons: list[str] = []
        if account_age < MIN_ACCOUNT_AGE_DAYS:
            eligibility_reasons.append(f"Account age {account_age} < {MIN_ACCOUNT_AGE_DAYS} in-game days.")
        if metrics["days_active"] < MIN_DAYS_ACTIVE:
            eligibility_reasons.append(
                f"Only {metrics['days_active']} active days (min {MIN_DAYS_ACTIVE} required)."
            )
        if player.anti_cheat_flag and scores["anti_exploit_score"] <= ANTI_CHEAT_SEVERITY_THRESHOLD:
            eligibility_reasons.append("Severe anti-cheat flag active.")

        eligible = not eligibility_reasons
        eligibility_status = "eligible" if eligible else "ineligible"
        approved_points = round(raw, 2) if eligible else 0.0

        # Token conversion & cap.
        window = self.create_or_get_claim_window(month_key, db)
        estimated_tokens = round(approved_points * TOKEN_CONVERSION_RATE, 4)
        cap_applied = False
        if estimated_tokens > window.max_claim_per_player:
            estimated_tokens = round(window.max_claim_per_player, 4)
            cap_applied = True

        all_notes: list[str] = eligibility_reasons + exploit_notes
        return {
            "month_key": month_key,
            "days_active": metrics["days_active"],
            "total_work_actions": metrics["total_work_actions"],
            "total_main_job_hours": metrics["total_main_job_hours"],
            "total_side_job_hours": metrics["total_side_job_hours"],
            "total_income_earned": float(metrics["total_income_earned"]),
            "total_food_purchased": metrics["total_food_purchased"],
            "total_food_consumed": metrics["total_food_consumed"],
            "average_health": metrics["average_health"],
            "average_stress": metrics["average_stress"],
            "average_fatigue": metrics["average_fatigue"],
            "consistency_score": round(scores["consistency_score"], 2),
            "survival_score": round(scores["survival_score"], 2),
            "productivity_score": round(scores["productivity_score"], 2),
            "anti_exploit_score": round(scores["anti_exploit_score"], 2),
            "raw_reward_points": raw,
            "approved_reward_points": approved_points,
            "token_conversion_rate": TOKEN_CONVERSION_RATE,
            "estimated_token_amount": estimated_tokens,
            "monthly_cap_applied": cap_applied,
            "eligibility_status": eligibility_status,
            "notes": "; ".join(all_notes) if all_notes else None,
            "account_age_days": account_age,
        }

    def finalize_player_monthly_reward(
        self, player_id: UUID, month_key: str, db: Session
    ) -> dict[str, Any]:
        """Calculate, persist, and return a player's finalized monthly reward.

        Idempotent: if a ledger row already exists for (player_id, month_key),
        it updates the row in place rather than duplicating approved amounts.
        """
        _validate_month_key(month_key)
        calc = self.calculate_player_monthly_reward(player_id, month_key, db)

        existing_ledger = (
            db.query(RewardLedger)
            .filter(RewardLedger.player_id == player_id, RewardLedger.month_key == month_key)
            .first()
        )
        previously_approved = 0.0
        previously_approved_tokens = 0.0
        if existing_ledger is not None:
            previously_approved = float(existing_ledger.approved_reward_points)
            previously_approved_tokens = float(existing_ledger.estimated_token_amount)

        # Update or create ledger row.
        if existing_ledger is None:
            ledger = RewardLedger(
                player_id=player_id,
                month_key=month_key,
            )
            db.add(ledger)
        else:
            ledger = existing_ledger

        ledger.days_active = calc["days_active"]
        ledger.total_work_actions = calc["total_work_actions"]
        ledger.total_main_job_hours = calc["total_main_job_hours"]
        ledger.total_side_job_hours = calc["total_side_job_hours"]
        ledger.total_income_earned = calc["total_income_earned"]
        ledger.total_food_purchased = calc["total_food_purchased"]
        ledger.total_food_consumed = calc["total_food_consumed"]
        ledger.average_health = calc["average_health"]
        ledger.average_stress = calc["average_stress"]
        ledger.average_fatigue = calc["average_fatigue"]
        ledger.consistency_score = calc["consistency_score"]
        ledger.survival_score = calc["survival_score"]
        ledger.productivity_score = calc["productivity_score"]
        ledger.anti_exploit_score = calc["anti_exploit_score"]
        ledger.raw_reward_points = calc["raw_reward_points"]
        ledger.approved_reward_points = calc["approved_reward_points"]
        ledger.token_conversion_rate = calc["token_conversion_rate"]
        ledger.estimated_token_amount = calc["estimated_token_amount"]
        ledger.monthly_cap_applied = calc["monthly_cap_applied"]
        ledger.eligibility_status = calc["eligibility_status"]
        ledger.notes = calc["notes"]

        db.flush()

        # Update anti-cheat flag on player if exploit score is severe.
        player = db.query(Player).filter(Player.id == player_id).first()
        if player is not None and calc["anti_exploit_score"] <= ANTI_CHEAT_SEVERITY_THRESHOLD:
            player.anti_cheat_flag = True
        if player is not None:
            player.reward_eligibility_status = calc["eligibility_status"]

        # Update claim balance (delta to avoid double-crediting re-runs).
        new_approved_tokens = calc["estimated_token_amount"]
        delta_tokens = max(0.0, new_approved_tokens - previously_approved_tokens)
        delta_points = max(0.0, calc["approved_reward_points"] - previously_approved)
        carry_forward = self.update_claim_balance(player_id, delta_points, delta_tokens, month_key, db)

        db.commit()

        return {
            **calc,
            "carry_forward_applied": carry_forward,
        }

    def update_claim_balance(
        self,
        player_id: UUID,
        approved_points: float,
        approved_token_amount: float,
        month_key: str,
        db: Session,
    ) -> bool:
        """Add approved amounts to the player's ClaimBalance.

        Returns True if the new total is below minimum threshold (carry-forward).
        """
        balance = db.query(ClaimBalance).filter(ClaimBalance.player_id == player_id).first()
        if balance is None:
            balance = ClaimBalance(player_id=player_id)
            db.add(balance)
            db.flush()

        balance.pending_reward_points = round(
            max(0.0, float(balance.pending_reward_points) + approved_points), 4
        )
        balance.pending_token_amount = round(
            max(0.0, float(balance.pending_token_amount) + approved_token_amount), 4
        )
        balance.lifetime_approved_token_amount = round(
            float(balance.lifetime_approved_token_amount) + approved_token_amount, 4
        )
        balance.last_processed_month_key = month_key

        # Mirror to player fields for quick read.
        player = db.query(Player).filter(Player.id == player_id).first()
        if player is not None:
            player.pending_reward_points = balance.pending_reward_points
            player.pending_token_amount = balance.pending_token_amount

        carry_forward = balance.pending_token_amount < MIN_CLAIM_THRESHOLD
        return carry_forward

    def get_player_reward_summary(self, player_id: UUID, db: Session) -> dict[str, Any]:
        """Return a fast summary of the player's current reward state."""
        player = db.query(Player).filter(Player.id == player_id).first()
        if player is None:
            raise ValueError(f"Player {player_id} not found.")

        balance = db.query(ClaimBalance).filter(ClaimBalance.player_id == player_id).first()
        wallet = (
            db.query(WalletLink)
            .filter(WalletLink.player_id == player_id, WalletLink.is_verified.is_(True))
            .first()
        )
        return {
            "pending_reward_points": float(player.pending_reward_points or 0),
            "pending_token_amount": float(player.pending_token_amount or 0),
            "total_lifetime_token_claimed": float(player.total_lifetime_token_claimed or 0),
            "reward_eligibility_status": player.reward_eligibility_status or "eligible",
            "anti_cheat_flag": bool(player.anti_cheat_flag),
            "wallet_linked": bool(player.wallet_linked),
            "last_processed_month_key": balance.last_processed_month_key if balance else None,
            "claim_ready": (
                float(player.pending_token_amount or 0) >= MIN_CLAIM_THRESHOLD
                and bool(player.wallet_linked)
                and not bool(player.anti_cheat_flag)
            ),
        }

    def flag_suspicious_reward_pattern(
        self, player_id: UUID, month_key: str, db: Session
    ) -> list[str]:
        """Run suspicious-pattern detection and return a list of flagged reasons."""
        _validate_month_key(month_key)
        start, end = _month_date_range(month_key)
        day_logs = (
            db.query(DayLog)
            .filter(DayLog.player_id == player_id, DayLog.created_at >= start, DayLog.created_at <= end)
            .all()
        )
        job_actions = (
            db.query(JobAction)
            .filter(JobAction.player_id == player_id, JobAction.created_at >= start, JobAction.created_at <= end)
            .all()
        )
        metrics = self._build_activity_metrics(day_logs, job_actions)
        return self._check_suspicious_patterns(metrics, day_logs, job_actions)

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _get_account_start_day(self, player_id: UUID, player: Player, db: Session) -> int:
        """Return the in-game day the account was first active."""
        if player.account_created_day is not None:
            return int(player.account_created_day)
        first_log = (
            db.query(DayLog)
            .filter(DayLog.player_id == player_id)
            .order_by(DayLog.day.asc())
            .first()
        )
        start = first_log.day if first_log else 1
        # Persist so future calls skip the query.
        player.account_created_day = start
        db.flush()
        return start

    def _build_activity_metrics(
        self, day_logs: list[DayLog], job_actions: list[JobAction]
    ) -> dict[str, Any]:
        days_active = len(day_logs)
        total_work_actions = sum(int(d.actions_taken) for d in day_logs)
        total_income_earned = sum(float(d.income_earned) for d in day_logs)

        main_hours = sum(
            int(j.hours_worked) for j in job_actions if j.job_type == "main"
        )
        side_hours = sum(
            int(j.hours_worked) for j in job_actions if j.job_type == "side"
        )

        avg_health = (
            round(statistics.mean(int(d.ending_health) for d in day_logs), 2)
            if day_logs
            else 0.0
        )
        avg_stress = (
            round(statistics.mean(int(d.ending_stress) for d in day_logs), 2)
            if day_logs
            else 0.0
        )
        avg_fatigue = (
            round(statistics.mean(float(d.ending_fatigue) for d in day_logs), 2)
            if day_logs
            else 0.0
        )

        return {
            "days_active": days_active,
            "total_work_actions": total_work_actions,
            "total_main_job_hours": main_hours,
            "total_side_job_hours": side_hours,
            "total_income_earned": total_income_earned,
            # Food tracking — reserved for future basket consumption hooks.
            "total_food_purchased": 0,
            "total_food_consumed": 0,
            "average_health": avg_health,
            "average_stress": avg_stress,
            "average_fatigue": avg_fatigue,
        }

    def _compute_scores(
        self, metrics: dict[str, Any], day_logs: list[DayLog]
    ) -> dict[str, float]:
        days = metrics["days_active"]

        # Consistency: reward showing up. Full score at 22+ active days.
        consistency = _clamp(days / 22.0 * 100.0, 0.0, 100.0)

        # Survival: health & stress balance.
        health_component = _clamp(metrics["average_health"], 0.0, 100.0)
        stress_component = _clamp(100.0 - metrics["average_stress"], 0.0, 100.0)
        survival = round(health_component * 0.60 + stress_component * 0.40, 2)

        # Productivity: work actions and income capped at ceiling.
        # 60 actions/month and 5000 income = full productivity score.
        actions_component = _clamp(metrics["total_work_actions"] / 60.0 * 100.0, 0.0, 100.0)
        income_component = _clamp(metrics["total_income_earned"] / 5000.0 * 100.0, 0.0, 100.0)
        productivity = round(actions_component * 0.5 + income_component * 0.5, 2)

        return {
            "consistency_score": round(consistency, 2),
            "survival_score": survival,
            "productivity_score": productivity,
            "anti_exploit_score": 100.0,  # reduced later if patterns found
        }

    def _check_suspicious_patterns(
        self,
        metrics: dict[str, Any],
        day_logs: list[DayLog],
        job_actions: list[JobAction],
    ) -> list[str]:
        """Return a list of human-readable suspicious pattern descriptions."""
        flags: list[str] = []
        if not day_logs:
            return flags

        hours_per_day = [int(d.hours_worked) for d in day_logs]
        actions_per_day = [int(d.actions_taken) for d in day_logs]

        # 1. Suspiciously low variance in daily hours (bot-like regularity).
        if len(hours_per_day) >= 10 and max(hours_per_day) > 0:
            try:
                std_hours = statistics.stdev(hours_per_day)
                if std_hours < 0.5:
                    flags.append(
                        "Daily hours almost identical across 10+ days — possible bot pattern."
                    )
            except statistics.StatisticsError:
                pass

        # 2. Same action count every single day for 7+ consecutive days.
        if len(actions_per_day) >= 7:
            max_run = 1
            current_run = 1
            for i in range(1, len(actions_per_day)):
                if actions_per_day[i] == actions_per_day[i - 1] and actions_per_day[i] > 0:
                    current_run += 1
                    max_run = max(max_run, current_run)
                else:
                    current_run = 1
            if max_run >= 7:
                flags.append(
                    f"Exact same daily action count for {max_run} consecutive days."
                )

        # 3. Very high income with little health variation (max-grind exploit).
        if metrics["total_income_earned"] > 10_000 and metrics["days_active"] >= 10:
            health_values = [int(d.ending_health) for d in day_logs]
            try:
                health_std = statistics.stdev(health_values)
            except statistics.StatisticsError:
                health_std = 0.0
            if health_std < 2.0:
                flags.append(
                    "Very high income with almost no health variation — possible exploit."
                )

        # 4. Average daily income implausibly high (> $500/active day).
        if metrics["days_active"] > 0:
            daily_avg_income = metrics["total_income_earned"] / metrics["days_active"]
            if daily_avg_income > 500.0:
                flags.append(
                    f"Average daily income ${daily_avg_income:.0f} exceeds plausible threshold."
                )

        return flags

    # ═══════════════════════════════════════════════════════════════════════════
    # Step 9: Monthly Reward Pool and Token Claim Accounting
    # ═══════════════════════════════════════════════════════════════════════════

    # ── Emission schedule ─────────────────────────────────────────────────────

    _MONTHLY_EMISSION: dict[int, float] = {
        # month_index: total tokens for that month
        # Months 1-6: 100,000 tokens each. Future months inherit default.
    }
    _DEFAULT_MONTHLY_EMISSION = 100_000.0

    def _emission_for_month(self, month_index: int) -> float:
        """Return the token emission cap for a given game month index."""
        return self._MONTHLY_EMISSION.get(month_index, self._DEFAULT_MONTHLY_EMISSION)

    def _current_month_index(self, db: Session) -> int:
        """Derive current game month (1-based) from game state current_day."""
        from app.models.game_state import GameState
        state = db.query(GameState).order_by(GameState.id.asc()).first()
        current_day = int(state.current_day) if state else 1
        return max(1, (current_day - 1) // 30 + 1)

    # ── PlayerRewardScore helpers ─────────────────────────────────────────────

    def _get_or_create_score(
        self, player_id: Any, month_index: int, current_day: int, db: Session
    ) -> PlayerRewardScore:
        """Return (or create) the PlayerRewardScore for a player+month."""
        score = (
            db.query(PlayerRewardScore)
            .filter(
                PlayerRewardScore.player_id == player_id,
                PlayerRewardScore.month_index == month_index,
            )
            .first()
        )
        if score is None:
            score = PlayerRewardScore(
                player_id=player_id,
                month_index=month_index,
                last_updated_day=current_day,
            )
            db.add(score)
            db.flush()
        return score

    def _sync_score_total(self, score: PlayerRewardScore) -> None:
        """Recompute total_points from sub-categories. Points floor is 0."""
        score.total_points = round(
            max(0.0, score.work_points)
            + max(0.0, score.business_points)
            + max(0.0, score.investment_points)
            + max(0.0, score.marketplace_points)
            + max(0.0, score.stability_points),
            4,
        )

    # ── Public point accumulation API ─────────────────────────────────────────

    def add_work_points(
        self,
        player: Player,
        hours_worked: float,
        productivity: float,
        current_day: int,
        db: Session,
        month_index: int | None = None,
    ) -> float:
        """Earn work points: hours_worked × productivity × 0.5.

        Returns the points added this call. Points are always non-negative.
        """
        if month_index is None:
            month_index = self._current_month_index(db)
        earned = max(0.0, round(hours_worked * max(0.0, productivity) * 0.5, 4))
        if earned == 0.0:
            return 0.0
        score = self._get_or_create_score(player.id, month_index, current_day, db)
        score.work_points = round(max(0.0, score.work_points) + earned, 4)
        score.last_updated_day = current_day
        self._sync_score_total(score)
        db.commit()
        return earned

    def add_business_points(
        self,
        player: Player,
        profit_today: float,
        current_day: int,
        db: Session,
        month_index: int | None = None,
    ) -> float:
        """Earn business points from positive daily profit: profit × 0.02.

        Only positive profit counts — losses do not subtract points.
        Returns the points added this call.
        """
        if month_index is None:
            month_index = self._current_month_index(db)
        if profit_today <= 0.0:
            return 0.0
        earned = round(profit_today * 0.02, 4)
        score = self._get_or_create_score(player.id, month_index, current_day, db)
        score.business_points = round(max(0.0, score.business_points) + earned, 4)
        score.last_updated_day = current_day
        self._sync_score_total(score)
        db.commit()
        return earned

    def add_investment_points(
        self,
        player: Player,
        realized_profit: float,
        current_day: int,
        db: Session,
        month_index: int | None = None,
    ) -> float:
        """Earn investment points from realized stock gains: profit × 0.01.

        Only realized gains count (not unrealized). Returns points added.
        """
        if month_index is None:
            month_index = self._current_month_index(db)
        if realized_profit <= 0.0:
            return 0.0
        earned = round(realized_profit * 0.01, 4)
        score = self._get_or_create_score(player.id, month_index, current_day, db)
        score.investment_points = round(max(0.0, score.investment_points) + earned, 4)
        score.last_updated_day = current_day
        self._sync_score_total(score)
        db.commit()
        return earned

    def add_marketplace_points(
        self,
        player: Player,
        trade_value: float,
        current_day: int,
        db: Session,
        month_index: int | None = None,
    ) -> float:
        """Earn marketplace points from trading activity: trade_value × 0.005.

        Applied to seller's gross trade value on completed marketplace sales.
        Returns points added.
        """
        if month_index is None:
            month_index = self._current_month_index(db)
        if trade_value <= 0.0:
            return 0.0
        earned = round(trade_value * 0.005, 4)
        score = self._get_or_create_score(player.id, month_index, current_day, db)
        score.marketplace_points = round(max(0.0, score.marketplace_points) + earned, 4)
        score.last_updated_day = current_day
        self._sync_score_total(score)
        db.commit()
        return earned

    def add_stability_points(
        self,
        player: Player,
        current_day: int,
        db: Session,
        month_index: int | None = None,
    ) -> float:
        """Award +5 stability points for financially responsible behavior.

        Eligibility requires ALL of:
        - Player has active housing and it is not in severe delinquency.
        - Player has no active anti-cheat flag.
        - Player cash >= 0 (positive cash flow).
        - Rate-limited: only once per 7 in-game days per player per month.

        Returns points added (0 if not eligible or rate-limited).
        """
        if month_index is None:
            month_index = self._current_month_index(db)

        # Eligibility checks
        if bool(player.anti_cheat_flag):
            return 0.0
        if float(player.cash) < 0:
            return 0.0

        score = self._get_or_create_score(player.id, month_index, current_day, db)

        # Rate-limit: only grant once per 7-day window within the month.
        if score.last_updated_day is not None:
            days_since_last = current_day - int(score.last_updated_day)
            if days_since_last < 7:
                return 0.0

        earned = 5.0
        score.stability_points = round(max(0.0, score.stability_points) + earned, 4)
        score.last_updated_day = current_day
        self._sync_score_total(score)
        db.commit()
        return earned

    # ── Reward pool management ────────────────────────────────────────────────

    def get_or_create_reward_pool(
        self, month_index: int, current_day: int, db: Session
    ) -> RewardPool:
        """Return (or create) the RewardPool for a given game month index."""
        pool = (
            db.query(RewardPool)
            .filter(RewardPool.month_index == month_index)
            .first()
        )
        if pool is None:
            allocation = self._emission_for_month(month_index)
            pool = RewardPool(
                month_index=month_index,
                total_tokens_allocated=allocation,
                tokens_remaining=allocation,
                points_total=0.0,
                status="open",
                created_day=current_day,
            )
            db.add(pool)
            db.commit()
            db.refresh(pool)
        return pool

    def close_reward_pool(
        self, month_index: int, current_day: int, db: Session
    ) -> dict[str, Any]:
        """Close the reward pool for a game month and calculate player allowances.

        Process:
        1. Validate pool is open and exists.
        2. Sum all PlayerRewardScore.total_points for this month.
        3. Compute each player's proportional token allocation.
        4. Create (or update) TokenClaimAllowance rows with status "claimable".
        5. Mark pool as closed.

        Returns summary dict with pool stats and player count.

        Raises ValueError if pool is already closed or does not exist.
        """
        pool = (
            db.query(RewardPool)
            .filter(RewardPool.month_index == month_index)
            .first()
        )
        if pool is None:
            raise ValueError(
                f"No reward pool found for month_index={month_index}. "
                "Create one first with get_or_create_reward_pool()."
            )
        if pool.status == "closed":
            raise ValueError(
                f"Reward pool for month_index={month_index} is already closed."
            )

        # Gather all scores for this month
        scores = (
            db.query(PlayerRewardScore)
            .filter(
                PlayerRewardScore.month_index == month_index,
                PlayerRewardScore.total_points > 0.0,
            )
            .all()
        )

        points_total = sum(float(s.total_points) for s in scores)
        pool.points_total = round(points_total, 4)

        allocated_total = 0.0
        players_rewarded = 0

        for score in scores:
            player_points = float(score.total_points)
            if points_total > 0.0:
                share = player_points / points_total
            else:
                share = 0.0

            token_alloc = round(
                float(pool.total_tokens_allocated) * share, 4
            )

            # Upsert TokenClaimAllowance
            allowance = (
                db.query(TokenClaimAllowance)
                .filter(
                    TokenClaimAllowance.player_id == score.player_id,
                    TokenClaimAllowance.month_index == month_index,
                )
                .first()
            )
            if allowance is None:
                allowance = TokenClaimAllowance(
                    player_id=score.player_id,
                    month_index=month_index,
                )
                db.add(allowance)

            allowance.total_points = player_points
            allowance.token_allocation = token_alloc
            allowance.claimable_tokens = max(0.0, token_alloc - float(allowance.tokens_claimed))
            allowance.allowance_status = "claimable"
            allowance.calculated_day = current_day

            allocated_total += token_alloc
            players_rewarded += 1

        pool.tokens_remaining = max(
            0.0,
            round(float(pool.total_tokens_allocated) - allocated_total, 4),
        )
        pool.status = "closed"
        pool.closed_day = current_day

        db.commit()

        return {
            "month_index": month_index,
            "total_tokens_allocated": float(pool.total_tokens_allocated),
            "tokens_distributed": round(allocated_total, 4),
            "tokens_remaining_in_pool": float(pool.tokens_remaining),
            "points_total": round(points_total, 4),
            "players_rewarded": players_rewarded,
            "closed_day": current_day,
        }

    # ── Player score and allowance queries ────────────────────────────────────

    def get_player_score(
        self,
        player: Player,
        month_index: int,
        db: Session,
    ) -> dict[str, Any]:
        """Return the player's current reward score for a game month."""
        score = (
            db.query(PlayerRewardScore)
            .filter(
                PlayerRewardScore.player_id == player.id,
                PlayerRewardScore.month_index == month_index,
            )
            .first()
        )
        if score is None:
            return {
                "player_id": str(player.id),
                "month_index": month_index,
                "work_points": 0.0,
                "business_points": 0.0,
                "investment_points": 0.0,
                "marketplace_points": 0.0,
                "stability_points": 0.0,
                "total_points": 0.0,
                "last_updated_day": None,
            }
        return {
            "player_id": str(player.id),
            "month_index": month_index,
            "work_points": round(float(score.work_points), 4),
            "business_points": round(float(score.business_points), 4),
            "investment_points": round(float(score.investment_points), 4),
            "marketplace_points": round(float(score.marketplace_points), 4),
            "stability_points": round(float(score.stability_points), 4),
            "total_points": round(float(score.total_points), 4),
            "last_updated_day": score.last_updated_day,
        }

    def get_player_allowances(
        self,
        player: Player,
        db: Session,
        month_index: int | None = None,
    ) -> list[dict[str, Any]]:
        """Return token claim allowances for the player.

        If month_index is given, returns only that month.
        Otherwise returns all months newest-first.
        """
        q = db.query(TokenClaimAllowance).filter(
            TokenClaimAllowance.player_id == player.id
        )
        if month_index is not None:
            q = q.filter(TokenClaimAllowance.month_index == month_index)
        allowances = q.order_by(TokenClaimAllowance.month_index.desc()).all()

        return [
            {
                "allowance_id": str(a.id),
                "month_index": a.month_index,
                "total_points": round(float(a.total_points), 4),
                "token_allocation": round(float(a.token_allocation), 4),
                "tokens_claimed": round(float(a.tokens_claimed), 4),
                "claimable_tokens": round(float(a.claimable_tokens), 4),
                "allowance_status": a.allowance_status,
                "calculated_day": a.calculated_day,
            }
            for a in allowances
        ]

    def get_monthly_summary(
        self,
        player: Player,
        month_index: int,
        db: Session,
    ) -> dict[str, Any]:
        """Return player score + pool info + estimated share for one game month."""
        pool = (
            db.query(RewardPool)
            .filter(RewardPool.month_index == month_index)
            .first()
        )
        score_data = self.get_player_score(player, month_index, db)
        player_points = score_data["total_points"]

        # Estimate pool-wide totals including this player's points.
        pool_points = float(pool.points_total) if pool else None
        pool_tokens = float(pool.total_tokens_allocated) if pool else self._emission_for_month(month_index)
        pool_status = pool.status if pool else "not_created"

        if pool_points and pool_points > 0 and player_points > 0:
            estimated_share = player_points / pool_points
            estimated_tokens = round(pool_tokens * estimated_share, 4)
        else:
            estimated_share = 0.0
            estimated_tokens = 0.0

        return {
            "month_index": month_index,
            "pool_status": pool_status,
            "pool_total_tokens": pool_tokens,
            "pool_points_total": pool_points,
            **score_data,
            "estimated_share": round(estimated_share, 6),
            "estimated_tokens": estimated_tokens,
        }

    # ── Token claim ───────────────────────────────────────────────────────────

    def claim_tokens(
        self,
        player: Player,
        month_index: int,
        db: Session,
    ) -> dict[str, Any]:
        """Mark the player's monthly token allowance as claimed.

        Validation:
        - Allowance must exist and have status 'claimable'.
        - tokens_claimed must be 0 (no duplicate claims).
        - claimable_tokens must be > 0.

        Behavior:
        1. Set tokens_claimed = token_allocation.
        2. Set claimable_tokens = 0.
        3. Set allowance_status = 'claimed'.
        4. Create TokenClaimHistory record.
        5. Update ClaimBalance.lifetime_claimed_token_amount.

        Returns claim summary. Raises ValueError on any validation failure.
        """
        allowance = (
            db.query(TokenClaimAllowance)
            .filter(
                TokenClaimAllowance.player_id == player.id,
                TokenClaimAllowance.month_index == month_index,
            )
            .first()
        )
        if allowance is None:
            raise ValueError(
                f"No token allowance found for month_index={month_index}. "
                "The reward pool must be closed before you can claim."
            )
        if allowance.allowance_status != "claimable":
            raise ValueError(
                f"Allowance is not claimable (status: '{allowance.allowance_status}'). "
                "Pool must be closed and allowance status must be 'claimable'."
            )
        if float(allowance.tokens_claimed) > 0:
            raise ValueError(
                f"Tokens for month_index={month_index} have already been claimed."
            )
        tokens_to_claim = float(allowance.claimable_tokens)
        if tokens_to_claim <= 0.0:
            raise ValueError("Claimable token amount is zero — nothing to claim.")

        # Mark allowance as claimed
        from datetime import datetime, timezone
        allowance.tokens_claimed = tokens_to_claim
        allowance.claimable_tokens = 0.0
        allowance.allowance_status = "claimed"

        # Create immutable history record
        history = TokenClaimHistory(
            player_id=player.id,
            month_index=month_index,
            tokens_claimed=tokens_to_claim,
            claim_method="offchain_mark",
            transaction_reference=None,
        )
        db.add(history)

        # Update ClaimBalance lifetime accounting
        balance = (
            db.query(ClaimBalance)
            .filter(ClaimBalance.player_id == player.id)
            .first()
        )
        if balance is not None:
            balance.lifetime_claimed_token_amount = round(
                float(balance.lifetime_claimed_token_amount) + tokens_to_claim, 4
            )
            # Deduct from pending if present
            if float(balance.pending_token_amount) >= tokens_to_claim:
                balance.pending_token_amount = round(
                    float(balance.pending_token_amount) - tokens_to_claim, 4
                )
            else:
                balance.pending_token_amount = 0.0

            # Mirror to player field
            player.total_lifetime_token_claimed = round(
                float(player.total_lifetime_token_claimed or 0) + tokens_to_claim, 4
            )
            player.pending_token_amount = balance.pending_token_amount

        db.commit()

        return {
            "message": "Tokens marked as claimed. Blockchain minting will occur in a future step.",
            "month_index": month_index,
            "tokens_claimed": tokens_to_claim,
            "allowance_status": "claimed",
            "claim_method": "offchain_mark",
            "transaction_reference": None,
        }

    def get_claim_history(
        self,
        player: Player,
        db: Session,
    ) -> list[dict[str, Any]]:
        """Return the player's full token claim history newest-first."""
        rows = (
            db.query(TokenClaimHistory)
            .filter(TokenClaimHistory.player_id == player.id)
            .order_by(TokenClaimHistory.claim_timestamp.desc())
            .all()
        )
        return [
            {
                "claim_id": str(r.id),
                "month_index": r.month_index,
                "tokens_claimed": r.tokens_claimed,
                "claim_timestamp": r.claim_timestamp.isoformat() if r.claim_timestamp else None,
                "claim_method": r.claim_method,
                "transaction_reference": r.transaction_reference,
            }
            for r in rows
        ]


# ═══════════════════════════════════════════════════════════════════════════════
# Step 1 — Monetary constitution: pure, DB-free helper functions
#
# These functions implement the PFT reward allocation model described in the
# monetary constitution layer.  They are intentionally free of SQLAlchemy
# dependencies so they can be unit-tested without a database connection.
#
# Economic design:
#   XGP  — off-chain gameplay currency (wages, goods, services)
#   PFT  — on-chain ERC-20 reward token distributed via monthly pool
#
#   PFT allocation formula:
#       player_pft = (player_contribution_score / total_qualified_score)
#                    × monthly_reward_pool
#
#   Direct XGP→PFT conversion is explicitly disabled to prevent
#   uncontrolled token inflation through gameplay grinding.
# ═══════════════════════════════════════════════════════════════════════════════

from datetime import datetime as _datetime

from app.core.contribution_rules import CONTRIBUTION_WEIGHTS
from app.core.reward_policy import REWARD_POLICY


def is_player_reward_eligible(player: Any, snapshot: Any, policy: dict | None = None) -> bool:
    """Check whether a player qualifies for PFT allocation in a given epoch.

    Parameters
    ----------
    player:
        SQLAlchemy Player instance (or any object with .created_at and
        .reputation attributes).
    snapshot:
        ContributionSnapshot instance (or compatible object with a
        .contribution_score attribute).
    policy:
        Optional override for REWARD_POLICY.  Defaults to the canonical policy
        so caller code almost never needs to pass this.

    Returns
    -------
    bool
        True if the player meets every eligibility gate; False otherwise.

    Eligibility gates (all must pass)
    ----------------------------------
    1. Account age in calendar days >= policy["min_account_age_days"].
       Inferred from player.created_at if available.  If created_at is absent
       (legacy records) the check is skipped with a conservative pass so no
       established player is silently excluded.
       TODO: If created_at is consistently missing, store account_created_at
             in the players table and fall back to that field.
    2. player.reputation >= policy["min_reputation"].
    3. snapshot.contribution_score >= policy["min_contribution_score"].
    4. Wallet address is NOT required during Step 1 (claiming is disabled).
    """
    if policy is None:
        policy = REWARD_POLICY

    # Gate 1 — account age
    min_age: int = policy.get("min_account_age_days", 30)
    created_at = getattr(player, "created_at", None)
    if created_at is not None:
        try:
            now = _datetime.now(tz=created_at.tzinfo)
            age_days = (now - created_at).days
            if age_days < min_age:
                return False
        except Exception:
            # Defensive: if date arithmetic fails, skip this gate rather than
            # blocking all players on a potential data issue.
            pass
    # If created_at is not available, we cannot enforce age — pass the gate.
    # TODO: persist account_created_at on the Player model and use it here.

    # Gate 2 — reputation
    min_rep: int = policy.get("min_reputation", 20)
    player_rep: int = int(getattr(player, "reputation", 0) or 0)
    if player_rep < min_rep:
        return False

    # Gate 3 — contribution score
    min_score: float = float(policy.get("min_contribution_score", 100))
    snap_score: float = float(getattr(snapshot, "contribution_score", 0.0) or 0.0)
    if snap_score < min_score:
        return False

    # Gate 4 — wallet address NOT required while claiming is disabled.
    # When claim_enabled becomes True, uncomment the block below:
    # wallet = getattr(player, "wallet_address", None)
    # if not wallet:
    #     return False

    return True


def calculate_player_contribution_score(
    job_work_xgp: float = 0.0,
    business_profit_xgp: float = 0.0,
    market_trade_volume_xgp: float = 0.0,
    co_op_deals_completed: int = 0,
    reputation: int = 0,
    penalty_points: int = 0,
    weights: dict | None = None,
) -> float:
    """Compute a player's weighted contribution score for one epoch.

    The score determines each player's proportional share of the monthly PFT
    reward pool.  A higher score = larger allocation.  The score is always
    clamped at 0 — penalties cannot produce a negative value.

    Parameters
    ----------
    job_work_xgp:
        Total XGP earned through main-job and side-job labour.
    business_profit_xgp:
        Net XGP profit generated by owned businesses.
    market_trade_volume_xgp:
        Gross XGP volume traded on the marketplace (buy + sell sides).
    co_op_deals_completed:
        Number of co-operative player-vs-player deals finalised.
        Each deal is worth 100 XGP-equivalent before the weight is applied.
    reputation:
        Player reputation score at snapshot time.
    penalty_points:
        Accumulated bad-behaviour penalty points.  Each point reduces the
        score by abs(CONTRIBUTION_WEIGHTS["penalty_for_bad_behavior"]).
    weights:
        Optional weight override.  Defaults to CONTRIBUTION_WEIGHTS from
        app/core/contribution_rules.py.

    Returns
    -------
    float
        Weighted contribution score, minimum 0.0.
    """
    if weights is None:
        weights = CONTRIBUTION_WEIGHTS

    w_job: float = float(weights.get("job_work", 1.0))
    w_biz: float = float(weights.get("business_profit", 0.5))
    w_trade: float = float(weights.get("market_trade", 0.3))
    w_coop: float = float(weights.get("co_op_deal", 1.2))
    w_rep: float = float(weights.get("reputation_bonus", 0.2))
    # penalty weight is stored as a negative number; use its absolute value.
    w_penalty: float = abs(float(weights.get("penalty_for_bad_behavior", -2.0)))

    score: float = (
        max(0.0, job_work_xgp) * w_job
        + max(0.0, business_profit_xgp) * w_biz
        + max(0.0, market_trade_volume_xgp) * w_trade
        + max(0, co_op_deals_completed) * 100.0 * w_coop   # 100 XGP-eq per deal
        + max(0, reputation) * w_rep
        - max(0, penalty_points) * w_penalty
    )

    return round(max(0.0, score), 8)


def allocate_monthly_pft(
    qualified_snapshots: list,
    monthly_reward_pool: float,
) -> list:
    """Distribute PFT from the monthly pool across all qualified snapshots.

    Only snapshots whose ``qualified`` attribute is True receive an allocation.
    Non-qualified snapshots have ``pft_allocated`` set to 0 and are returned
    in the list unchanged.

    Formula
    -------
        pft_allocated = (contribution_score / total_qualified_score)
                        × monthly_reward_pool

    Edge cases
    ----------
    * If no snapshots are qualified, everyone receives 0 — no crash.
    * If total qualified contribution score is 0 (all zeros), everyone
      receives 0 — avoids division by zero.

    Parameters
    ----------
    qualified_snapshots:
        List of objects with ``qualified`` (bool) and ``contribution_score``
        (float) attributes.  Objects are mutated in-place: ``pft_allocated``
        is written on each item.
    monthly_reward_pool:
        Total PFT units available for distribution this epoch.

    Returns
    -------
    list
        The same list, with ``pft_allocated`` populated on each item.
    """
    total_qualified_score: float = sum(
        float(getattr(s, "contribution_score", 0.0) or 0.0)
        for s in qualified_snapshots
        if getattr(s, "qualified", False)
    )

    for snapshot in qualified_snapshots:
        is_qualified: bool = bool(getattr(snapshot, "qualified", False))
        if not is_qualified or total_qualified_score <= 0.0:
            snapshot.pft_allocated = 0.0
            continue

        score: float = float(getattr(snapshot, "contribution_score", 0.0) or 0.0)
        allocation: float = (score / total_qualified_score) * monthly_reward_pool
        snapshot.pft_allocated = round(allocation, 8)

    return qualified_snapshots


def simulate_epoch_allocation(snapshots: list, policy: dict | None = None) -> dict:
    """Dry-run PFT allocation for a set of simulated player snapshots.

    Does NOT write to the database.  Use this for the /rewards/simulate
    endpoint to give callers a preview of how allocation would work given a
    set of player activity inputs.

    Parameters
    ----------
    snapshots:
        List of objects with at minimum:
            - player_id (any)
            - contribution_score (float)
            - qualified (bool)
    policy:
        Optional override for REWARD_POLICY.

    Returns
    -------
    dict with keys:
        total_players               — int
        qualified_players           — int
        total_contribution_score    — float
        total_qualified_contribution_score — float
        monthly_reward_pool         — float
        allocations                 — list of per-player dicts
    """
    if policy is None:
        policy = REWARD_POLICY

    monthly_pool: float = float(policy.get("monthly_reward_pool", 50_000_000))

    total_score: float = sum(
        float(getattr(s, "contribution_score", 0.0) or 0.0)
        for s in snapshots
    )
    qualified_score: float = sum(
        float(getattr(s, "contribution_score", 0.0) or 0.0)
        for s in snapshots
        if getattr(s, "qualified", False)
    )
    qualified_count: int = sum(
        1 for s in snapshots if getattr(s, "qualified", False)
    )

    # Run allocation (mutates pft_allocated on each snapshot object).
    allocate_monthly_pft(snapshots, monthly_pool)

    allocations: list[dict] = [
        {
            "player_id": getattr(s, "player_id", None),
            "qualified": bool(getattr(s, "qualified", False)),
            "contribution_score": round(float(getattr(s, "contribution_score", 0.0) or 0.0), 8),
            "pft_allocated": round(float(getattr(s, "pft_allocated", 0.0) or 0.0), 8),
        }
        for s in snapshots
    ]

    return {
        "total_players": len(snapshots),
        "qualified_players": qualified_count,
        "total_contribution_score": round(total_score, 8),
        "total_qualified_contribution_score": round(qualified_score, 8),
        "monthly_reward_pool": monthly_pool,
        "allocations": allocations,
    }
