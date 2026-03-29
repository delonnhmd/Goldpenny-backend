"""Step 37 catalog for bounded in-game consumer borrowing offers."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BorrowingOfferTemplate:
    """Static template describing one abstract borrowing product family."""

    offer_key: str
    offer_family: str
    headline: str
    principal_range_xgp: tuple[float, float]
    apr_band: tuple[float, float]
    fee_band: tuple[float, float]
    term_days_range: tuple[int, int]
    approval_difficulty: int
    credit_min_hint: int
    delinquency_sensitivity: float
    payment_structure: str
    rollover_allowed: bool
    risk_label: str
    short_summary: str


BORROWING_OFFER_CATALOG: tuple[BorrowingOfferTemplate, ...] = (
    BorrowingOfferTemplate(
        offer_key="small_personal_installment",
        offer_family="mainstream",
        headline="Small Personal Installment",
        principal_range_xgp=(120.0, 900.0),
        apr_band=(0.11, 0.24),
        fee_band=(0.01, 0.04),
        term_days_range=(45, 150),
        approval_difficulty=2,
        credit_min_hint=610,
        delinquency_sensitivity=0.35,
        payment_structure="daily_equal",
        rollover_allowed=False,
        risk_label="moderate",
        short_summary="Balanced option with manageable payments when credit and stability hold.",
    ),
    BorrowingOfferTemplate(
        offer_key="basic_credit_line",
        offer_family="mainstream",
        headline="Basic Credit Line",
        principal_range_xgp=(90.0, 650.0),
        apr_band=(0.10, 0.22),
        fee_band=(0.00, 0.03),
        term_days_range=(30, 90),
        approval_difficulty=2,
        credit_min_hint=600,
        delinquency_sensitivity=0.40,
        payment_structure="daily_equal",
        rollover_allowed=True,
        risk_label="moderate",
        short_summary="Flexible bridge when discipline is strong; can become expensive if reused often.",
    ),
    BorrowingOfferTemplate(
        offer_key="paycheck_advance",
        offer_family="mainstream",
        headline="Paycheck Advance",
        principal_range_xgp=(60.0, 420.0),
        apr_band=(0.08, 0.19),
        fee_band=(0.01, 0.03),
        term_days_range=(14, 45),
        approval_difficulty=1,
        credit_min_hint=560,
        delinquency_sensitivity=0.30,
        payment_structure="short_cycle",
        rollover_allowed=False,
        risk_label="low",
        short_summary="Fast bridge for near-term liquidity gaps; useful when paid down quickly.",
    ),
    BorrowingOfferTemplate(
        offer_key="micro_emergency_loan",
        offer_family="mainstream",
        headline="Low-Limit Emergency Loan",
        principal_range_xgp=(40.0, 320.0),
        apr_band=(0.14, 0.30),
        fee_band=(0.02, 0.05),
        term_days_range=(14, 60),
        approval_difficulty=1,
        credit_min_hint=520,
        delinquency_sensitivity=0.45,
        payment_structure="daily_equal",
        rollover_allowed=False,
        risk_label="moderate",
        short_summary="Small survival option when cash is thin; short terms keep pressure visible.",
    ),
    BorrowingOfferTemplate(
        offer_key="high_cost_short_term",
        offer_family="riskier_survival",
        headline="High-Cost Short-Term Loan",
        principal_range_xgp=(80.0, 540.0),
        apr_band=(0.35, 0.75),
        fee_band=(0.06, 0.14),
        term_days_range=(7, 30),
        approval_difficulty=1,
        credit_min_hint=450,
        delinquency_sensitivity=0.65,
        payment_structure="short_cycle",
        rollover_allowed=True,
        risk_label="high",
        short_summary="Can prevent immediate collapse, but future burden rises quickly.",
    ),
    BorrowingOfferTemplate(
        offer_key="merchant_cash_bridge",
        offer_family="riskier_survival",
        headline="Merchant Cash Bridge",
        principal_range_xgp=(140.0, 760.0),
        apr_band=(0.30, 0.60),
        fee_band=(0.05, 0.12),
        term_days_range=(14, 50),
        approval_difficulty=3,
        credit_min_hint=520,
        delinquency_sensitivity=0.70,
        payment_structure="revenue_share_proxy",
        rollover_allowed=False,
        risk_label="high",
        short_summary="Useful for business cash crunches but can squeeze future margins.",
    ),
    BorrowingOfferTemplate(
        offer_key="penalty_heavy_bridge",
        offer_family="riskier_survival",
        headline="Penalty-Heavy Bridge Loan",
        principal_range_xgp=(100.0, 600.0),
        apr_band=(0.40, 0.90),
        fee_band=(0.08, 0.18),
        term_days_range=(7, 28),
        approval_difficulty=1,
        credit_min_hint=420,
        delinquency_sensitivity=0.85,
        payment_structure="short_cycle",
        rollover_allowed=True,
        risk_label="very_high",
        short_summary="Last-resort option; strong near-term relief with heavy downside if repeated.",
    ),
    BorrowingOfferTemplate(
        offer_key="friend_family_support",
        offer_family="soft_support",
        headline="Friend/Family Support Advance",
        principal_range_xgp=(40.0, 260.0),
        apr_band=(0.00, 0.06),
        fee_band=(0.00, 0.01),
        term_days_range=(30, 120),
        approval_difficulty=2,
        credit_min_hint=430,
        delinquency_sensitivity=0.25,
        payment_structure="daily_equal",
        rollover_allowed=False,
        risk_label="low",
        short_summary="Lower-cost support path with social reliability limits.",
    ),
    BorrowingOfferTemplate(
        offer_key="employer_shift_advance",
        offer_family="soft_support",
        headline="Employer Shift Advance",
        principal_range_xgp=(80.0, 360.0),
        apr_band=(0.03, 0.12),
        fee_band=(0.01, 0.03),
        term_days_range=(14, 60),
        approval_difficulty=2,
        credit_min_hint=500,
        delinquency_sensitivity=0.35,
        payment_structure="short_cycle",
        rollover_allowed=False,
        risk_label="moderate",
        short_summary="Moderate bridge for workers with stable schedules.",
    ),
    BorrowingOfferTemplate(
        offer_key="temporary_payment_relief",
        offer_family="soft_support",
        headline="Temporary Payment Relief Arrangement",
        principal_range_xgp=(60.0, 320.0),
        apr_band=(0.05, 0.16),
        fee_band=(0.01, 0.04),
        term_days_range=(30, 120),
        approval_difficulty=3,
        credit_min_hint=480,
        delinquency_sensitivity=0.30,
        payment_structure="deferred_start",
        rollover_allowed=False,
        risk_label="moderate",
        short_summary="Reduces immediate burden while extending future obligations.",
    ),
)

