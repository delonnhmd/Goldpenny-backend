"""app/engine/retention_engine.py — Step 69: Retention Engine.

Pure calculation layer.  No DB access.  Called by daily_settlement_service
at the tail of settle_player_day; results are embedded in summary_payload
and flow automatically through the settlement response and summary endpoint.
"""

from __future__ import annotations

# ── Pressure thresholds ───────────────────────────────────────────────────────
_CASH_CRITICAL = 40.0          # xgp — below this → critical flag
_CASH_LOW = 120.0              # xgp — below this → warning flag
_STRESS_CRITICAL = 75          # 0–100 scale
_STRESS_HIGH = 55
_HEALTH_LOW = 60
_LAYOFF_RISK_THRESHOLD = 0.25  # 25 % → job instability flag

# ── Streak bonus tiers (bounded, non-exploitable) ─────────────────────────────
# Applied only to the settlement outcome summary; actual cash/stress mutations
# are performed by the settlement service after reading streak_info.
_STREAK_TIERS = [
    {"min_streak": 7, "income_boost_pct": 0.03, "income_cap_xgp": 30.0, "stress_relief": 2},
    {"min_streak": 4, "income_boost_pct": 0.02, "income_cap_xgp": 20.0, "stress_relief": 1},
    {"min_streak": 2, "income_boost_pct": 0.00, "income_cap_xgp":  0.0, "stress_relief": 1},
]

# ── Opportunity carryover rules ───────────────────────────────────────────────
# category → (persist_probability 0–1, max_ttl_days, can_evolve bool)
_CARRY_RULES: dict[str, tuple[float, int, bool]] = {
    "job_upgrade":    (0.80, 3, True),
    "side_income":    (0.60, 2, False),
    "investment":     (0.50, 2, True),
    "debt_relief":    (0.90, 4, False),
    "skill_training": (0.70, 3, False),
    "housing":        (0.85, 5, False),
    "default":        (0.50, 2, False),
}


# ─────────────────────────────────────────────────────────────────────────────
# Public helpers
# ─────────────────────────────────────────────────────────────────────────────

def compute_next_day_pressure_flags(
    player_state: dict,
    settlement_result: dict,
) -> list[dict]:
    """
    Generate pressure flags that describe tomorrow's risk landscape.

    Each flag is a dict with:
      flag_key   — machine-readable identifier
      severity   — "critical" | "high" | "info"
      message    — player-facing sentence
      action_hint — one-sentence suggested action

    Flags are derived strictly from real player state; no synthetic alerts.
    """
    flags: list[dict] = []

    cash = float(player_state.get("cash", 9999))
    stress = int(player_state.get("stress", 0))
    health = int(player_state.get("health", 100))
    distress_state = str(player_state.get("distress_state", "stable"))
    layoff_risk = float(settlement_result.get("layoff_risk_pct", 0.0))
    pressure_label = str(settlement_result.get("payment_pressure_label", "manageable"))
    debt_payment_missed = bool(settlement_result.get("debt_payment_missed", False))

    # ── Cash pressure ────────────────────────────────────────────────────────
    if cash < _CASH_CRITICAL:
        flags.append({
            "flag_key": "critical_cash",
            "severity": "critical",
            "message": (
                f"Cash is critically low ({cash:.0f} xgp). "
                "Missing tomorrow's essential costs risks a debt spiral."
            ),
            "action_hint": "Prioritise a work shift before any discretionary spend tomorrow.",
        })
    elif cash < _CASH_LOW:
        flags.append({
            "flag_key": "low_cash",
            "severity": "high",
            "message": (
                f"Cash reserve is thin ({cash:.0f} xgp). "
                "One missed income day could start a shortfall."
            ),
            "action_hint": "Work tomorrow before spending on non-essentials.",
        })

    # ── Stress ───────────────────────────────────────────────────────────────
    if stress >= _STRESS_CRITICAL:
        flags.append({
            "flag_key": "critical_stress",
            "severity": "critical",
            "message": (
                f"Stress is dangerously high ({stress}/100). "
                "Productivity will take a significant hit tomorrow."
            ),
            "action_hint": "Rest before working. Consider skipping overtime tomorrow.",
        })
    elif stress >= _STRESS_HIGH:
        flags.append({
            "flag_key": "high_stress",
            "severity": "high",
            "message": f"Stress is elevated ({stress}/100). Recovery tonight matters.",
            "action_hint": "Avoid back-to-back shifts tomorrow.",
        })

    # ── Health ───────────────────────────────────────────────────────────────
    if health < _HEALTH_LOW:
        flags.append({
            "flag_key": "low_health",
            "severity": "high",
            "message": (
                f"Health is declining ({health}/100). "
                "Medical risk is rising and may reduce income."
            ),
            "action_hint": "Buy essentials and protein basket before working tomorrow.",
        })

    # ── Employment risk ──────────────────────────────────────────────────────
    if layoff_risk >= _LAYOFF_RISK_THRESHOLD:
        flags.append({
            "flag_key": "job_instability",
            "severity": "high",
            "message": (
                f"Layoff risk is elevated ({layoff_risk * 100:.0f} %). "
                "Job security may change before next pay cycle."
            ),
            "action_hint": (
                "Check the job market brief tomorrow for alternative openings."
            ),
        })

    # ── Payment pressure ─────────────────────────────────────────────────────
    if pressure_label in ("stressed", "critical", "default_risk"):
        flags.append({
            "flag_key": "payment_pressure",
            "severity": "high",
            "message": (
                f"Financial pressure is '{pressure_label}'. "
                "Obligations are consuming a large share of income."
            ),
            "action_hint": "Review debt obligations in the brief before spending tomorrow.",
        })

    # ── Delinquency ──────────────────────────────────────────────────────────
    if debt_payment_missed:
        flags.append({
            "flag_key": "debt_delinquency",
            "severity": "critical",
            "message": "A debt payment was missed today. Late fees and credit damage carry forward.",
            "action_hint": "Make catching up on the missed payment your first priority tomorrow.",
        })

    # ── Financial distress state ──────────────────────────────────────────────
    if distress_state not in ("stable", "recovering"):
        flags.append({
            "flag_key": "financial_distress",
            "severity": "high",
            "message": (
                f"Financial distress state is '{distress_state}'. "
                "Recovery path must be prioritised."
            ),
            "action_hint": "Focus on debt payments and income stability before discretionary spend.",
        })

    return flags


def compute_opportunity_carryover(
    opportunities: list[dict],
    day_number: int,
) -> dict:
    """
    Process a list of opportunity dicts from the previous day.

    Returns:
      carried  — opportunities that persist to tomorrow
      evolved  — opportunities that have become more urgent this cycle
      expired  — opportunities that closed or timed out
    """
    carried: list[dict] = []
    evolved: list[dict] = []
    expired: list[dict] = []

    for opp in opportunities:
        category = str(opp.get("category", "default"))
        persist_prob, max_ttl, can_evolve = _CARRY_RULES.get(
            category, _CARRY_RULES["default"]
        )
        ttl_remaining = int(opp.get("ttl_days_remaining", 1))

        if ttl_remaining <= 0:
            expired.append({**opp, "expiry_reason": "ttl_expired"})
            continue

        # Deterministic carry decision: hash the key + day to avoid randomness.
        carry_score = (hash(str(opp.get("opportunity_key", "x")) + str(day_number)) % 100) / 100.0
        if carry_score > persist_prob:
            expired.append({**opp, "expiry_reason": "opportunity_closed"})
            continue

        updated = {**opp, "ttl_days_remaining": ttl_remaining - 1, "carried_from_day": day_number}

        if can_evolve and ttl_remaining == max_ttl - 1:
            updated["evolved"] = True
            updated["evolution_note"] = "Urgency increasing — window is narrowing."
            evolved.append(updated)
        else:
            carried.append(updated)

    return {"carried": carried, "evolved": evolved, "expired": expired}


def compute_streak_bonus(streak_days: int, base_income: float) -> dict:
    """
    Return a bounded streak bonus derived from `streak_days`.

    income_boost_xgp is capped at the tier's income_cap_xgp, never exceeding
    the raw pct calculation AND the hard cap simultaneously.
    Returns `active: False` when streak is below the lowest threshold.
    """
    for tier in _STREAK_TIERS:
        if streak_days >= tier["min_streak"]:
            raw_boost = base_income * tier["income_boost_pct"]
            capped_boost = min(raw_boost, tier["income_cap_xgp"])
            return {
                "streak_days": streak_days,
                "income_boost_xgp": round(capped_boost, 4),
                "stress_reduction_bonus": int(tier["stress_relief"]),
                "tier_label": f"streak_{tier['min_streak']}plus",
                "active": True,
            }
    return {
        "streak_days": streak_days,
        "income_boost_xgp": 0.0,
        "stress_reduction_bonus": 0,
        "tier_label": "no_streak",
        "active": False,
    }


def compute_return_trigger_messages(
    pressure_flags: list[dict],
    carryover: dict,
    streak_info: dict,
) -> list[str]:
    """
    Compose up to four plain-text strings intended for future notification use.
    No push logic is executed here — these are stored data only.
    """
    messages: list[str] = []

    critical = [f for f in pressure_flags if f.get("severity") == "critical"]
    high = [f for f in pressure_flags if f.get("severity") == "high"]

    if critical:
        messages.append(f"Critical: {critical[0]['message']}")
    elif high:
        messages.append(f"Warning: {high[0]['message']}")

    carried = carryover.get("carried", []) + carryover.get("evolved", [])
    if carried:
        count = len(carried)
        cat = carried[0].get("category", "opportunity")
        messages.append(
            f"{count} open opportunit{'ies' if count > 1 else 'y'} waiting — "
            f"including a {cat} signal."
        )

    evolved = carryover.get("evolved", [])
    if evolved:
        note = evolved[0].get("evolution_note", "Opportunity window narrowing.")
        messages.append(note)

    if streak_info.get("active"):
        days = streak_info.get("streak_days", 0)
        boost = streak_info.get("income_boost_xgp", 0.0)
        if boost > 0:
            messages.append(
                f"{days}-day streak active — +{boost:.1f} xgp bonus on your next work shift."
            )
        else:
            messages.append(
                f"{days}-day streak active — stress recovers slightly faster tonight."
            )

    return messages[:4]  # hard cap: at most 4 messages


def build_retention_summary(
    player_state: dict,
    settlement_result: dict,
    streak_days: int,
    opportunities: list[dict] | None = None,
) -> dict:
    """
    Top-level entry point called by daily_settlement_service.

    Returns a self-contained dict that is embedded in summary_payload under
    the key ``retention_summary``.  All sub-functions are pure; this function
    performs no DB access.
    """
    day_number = int(player_state.get("day_number", 1))
    pressure_flags = compute_next_day_pressure_flags(player_state, settlement_result)
    carryover = compute_opportunity_carryover(opportunities or [], day_number)
    streak_info = compute_streak_bonus(streak_days, float(settlement_result.get("income_xgp", 0.0)))
    return_messages = compute_return_trigger_messages(pressure_flags, carryover, streak_info)

    return {
        "next_day_pressure_flags": pressure_flags,
        "carryover_opportunities": carryover,
        "streak_info": streak_info,
        "return_trigger_messages": return_messages,
        "day_number": day_number,
        "has_critical_flags": any(f.get("severity") == "critical" for f in pressure_flags),
        "total_carried_opportunities": len(carryover.get("carried", []) + carryover.get("evolved", [])),
    }
