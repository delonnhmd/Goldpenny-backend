"""Step 37 consumer borrowing response schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class BorrowingEligibilityProfileResponse(BaseModel):
    player_id: str
    as_of_date: str
    day_number: int
    borrowing_access_score: float
    credit_access_tier: str
    emergency_liquidity_label: str
    max_safe_borrow_amount_xgp: float
    estimated_risk_pricing_band: str
    recent_distress_penalty: float
    dependence_risk_score: float = 0.0
    active_loan_count: int = 0
    repeat_borrowing_count_30d: int = 0
    last_updated_on: int
    debug_meta: dict[str, Any] = Field(default_factory=dict)


class EmergencyLiquidityStateResponse(BaseModel):
    player_id: str
    as_of_date: str
    day_number: int
    days_to_cash_stress: float
    days_to_payment_failure: float
    liquidity_gap_xgp: float
    bridge_need_label: str
    survival_borrowing_pressure_label: str
    preferred_relief_type: str
    short_summary: str
    debug_meta: dict[str, Any] = Field(default_factory=dict)


class BorrowingOfferResponse(BaseModel):
    offer_key: str
    offer_family: str
    headline: str
    approval_likelihood_label: str
    principal_offered_xgp: float
    estimated_total_cost_xgp: float
    estimated_repay_xgp: float
    term_days: int
    term_label: str
    apr_pct: float
    fee_pct: float
    payment_burden_label: str
    risk_label: str
    emergency_usefulness_label: str
    hidden_danger_summary: str
    rollover_allowed: bool = False
    short_summary: str
    locked: bool = False
    locked_reason: str | None = None
    debug_meta: dict[str, Any] = Field(default_factory=dict)


class BorrowingOptionsResponse(BaseModel):
    player_id: str
    as_of_date: str
    day_number: int
    items: list[BorrowingOfferResponse] = Field(default_factory=list)
    debug_meta: dict[str, Any] = Field(default_factory=dict)


class BorrowingRiskSummaryResponse(BaseModel):
    player_id: str
    as_of_date: str
    risk_label: str
    short_term_relief_label: str
    future_burden_label: str
    credit_protection_value_label: str
    top_risk_driver: str
    top_reason_to_avoid: str
    top_reason_to_consider: str
    short_summary: str
    debug_meta: dict[str, Any] = Field(default_factory=dict)


class BorrowingPressureSummaryResponse(BaseModel):
    player_id: str
    as_of_date: str
    current_liquidity_pressure_label: str
    best_available_option_label: str
    worst_trap_warning: str
    practical_current_actions: list[str] = Field(default_factory=list)
    short_recommendation: str
    future_locked_options: list[str] = Field(default_factory=list)
    debug_meta: dict[str, Any] = Field(default_factory=dict)


class BorrowingDecisionRequest(BaseModel):
    offer_key: str
    principal_requested_xgp: float | None = None


class BorrowingDecisionResponse(BaseModel):
    player_id: str
    as_of_date: str
    day_number: int
    offer_key: str
    offer_family: str
    accepted: bool
    loan_account_id: str
    cash_before_xgp: float
    cash_after_xgp: float
    debt_before_xgp: float
    debt_after_xgp: float
    principal_accepted_xgp: float
    estimated_total_cost_xgp: float
    scheduled_daily_payment_xgp: float
    risk_label: str
    short_term_relief_label: str
    future_burden_label: str
    eligibility_profile_after: BorrowingEligibilityProfileResponse
    liquidity_state_after: EmergencyLiquidityStateResponse
    risk_summary_after: BorrowingRiskSummaryResponse
    debug_meta: dict[str, Any] = Field(default_factory=dict)


class PlayerLoanAccountsResponse(BaseModel):
    player_id: str
    entries: list[dict[str, Any]] = Field(default_factory=list)
    debug_meta: dict[str, Any] = Field(default_factory=dict)


class PlayerBorrowingHistoryResponse(BaseModel):
    player_id: str
    as_of_date: str
    entries: list[dict[str, Any]] = Field(default_factory=list)
    debug_meta: dict[str, Any] = Field(default_factory=dict)


class ConsumerBorrowingSystemSummaryResponse(BaseModel):
    player_id: str
    as_of_date: str
    day_number: int
    eligibility_profile: BorrowingEligibilityProfileResponse
    liquidity_state: EmergencyLiquidityStateResponse
    options: BorrowingOptionsResponse
    risk_summary: BorrowingRiskSummaryResponse
    pressure_summary: BorrowingPressureSummaryResponse
    loan_accounts: PlayerLoanAccountsResponse
    history: PlayerBorrowingHistoryResponse
    debug_meta: dict[str, Any] = Field(default_factory=dict)
