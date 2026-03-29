"""Tunable constants for Step 20 financial distress and recovery."""

from __future__ import annotations

from decimal import Decimal

CREDIT_SCORE_MIN = 300
CREDIT_SCORE_MAX = 850

DISTRESS_THRESHOLDS = {
    "stable": Decimal("24.9999"),
    "stretched": Decimal("49.9999"),
    "distressed": Decimal("74.9999"),
    "critical": Decimal("100.0000"),
}

DISTRESS_STATES = ("stable", "stretched", "distressed", "critical")

MAX_DAILY_DISTRESS_RELIEF = Decimal("12.0")
MAX_DAILY_DISTRESS_PAIN = Decimal("18.0")

BASE_LATE_FEE_XGP = Decimal("3.00")
MAX_LATE_FEE_XGP = Decimal("35.00")
UNDERPAID_LATE_FEE_FACTOR = Decimal("0.60")

PAYMENT_PLAN_DISTRESS_RELIEF = Decimal("4.50")
PAYMENT_PLAN_CREDIT_DRAG = -1

BORROWING_COST_MIN = Decimal("1.00")
BORROWING_COST_MAX = Decimal("1.80")
OPPORTUNITY_ACCESS_PENALTY_MAX = Decimal("0.30")
BUSINESS_RISK_PENALTY_MAX = Decimal("0.35")
CAREER_PROGRESS_PENALTY_MAX = Decimal("0.25")

RECOVERY_ACTIONS = {
    "payment_plan_enroll",
    "business_spending_cut",
    "housing_downshift_recommendation",
    "inventory_freeze",
    "extra_work_push",
    "defer_training",
    "emergency_savings_mode",
}
