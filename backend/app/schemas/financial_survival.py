"""Step 36 financial survival response schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class PlayerObligationProfileResponse(BaseModel):
    player_id: str
    as_of_date: str
    day_number: int
    required_monthly_obligation_xgp: float
    required_daily_burden_xgp: float
    debt_minimum_obligation_xgp: float
    housing_obligation_xgp: float
    business_overhead_obligation_xgp: float
    loan_obligation_xgp: float = 0.0
    insurance_basic_obligation_xgp: float
    obligation_load_ratio: float
    liquidity_buffer_days: float
    payment_pressure_label: str
    last_updated_on: int
    debug_meta: dict[str, Any] = Field(default_factory=dict)


class PaymentRiskStateResponse(BaseModel):
    player_id: str
    as_of_date: str
    day_number: int
    due_obligations: list[dict[str, Any]] = Field(default_factory=list)
    full_pay_feasible: bool
    partial_pay_feasible: bool
    likely_stress_impact: str
    late_fee_exposure_xgp: float
    delinquency_exposure: str
    short_recommendation: str
    debug_meta: dict[str, Any] = Field(default_factory=dict)


class DelinquencyStateResponse(BaseModel):
    player_id: str
    as_of_date: str
    day_number: int
    current_delinquency_stage: str
    survival_status_label: str
    missed_payment_count_30d: int
    late_payment_count_30d: int
    days_under_payment_stress: int
    last_missed_obligation_type: str | None = None
    credit_pressure_score: float
    credit_pressure_label: str
    financial_distress_score: float
    last_updated_on: int | None = None
    last_updated_date: str | None = None
    debug_meta: dict[str, Any] = Field(default_factory=dict)


class CreditImpactSummaryResponse(BaseModel):
    credit_score_before: int
    credit_score_after: int
    credit_delta: int
    impact_label: str
    primary_driver: str
    future_borrowing_pressure_label: str
    short_summary: str
    debug_meta: dict[str, Any] = Field(default_factory=dict)


class FinancialSurvivalSummaryResponse(BaseModel):
    player_id: str
    as_of_date: str
    survival_status_label: str
    payment_pressure_label: str
    credit_pressure_label: str
    liquidity_buffer_label: str
    top_distress_driver: str
    top_stabilizer: str
    practical_current_actions: list[str] = Field(default_factory=list)
    short_summary: str
    debug_meta: dict[str, Any] = Field(default_factory=dict)


class FinancialSurvivalPaymentHistoryResponse(BaseModel):
    player_id: str
    as_of_date: str
    entries: list[dict[str, Any]] = Field(default_factory=list)
    trailing_7d_missed_payments: int = 0
    trailing_7d_late_payments: int = 0
    trailing_7d_avg_obligation_load_ratio: float = 0.0
    trailing_7d_avg_liquidity_buffer_days: float = 0.0
    trailing_7d_credit_change: int = 0
    debug_meta: dict[str, Any] = Field(default_factory=dict)


class FinancialSurvivalSystemSummaryResponse(BaseModel):
    player_id: str
    as_of_date: str
    day_number: int
    obligation_profile: PlayerObligationProfileResponse
    payment_risk_state: PaymentRiskStateResponse
    delinquency_state: DelinquencyStateResponse
    credit_impact: CreditImpactSummaryResponse
    survival_summary: FinancialSurvivalSummaryResponse
    payment_history: FinancialSurvivalPaymentHistoryResponse
    recent_payment: dict[str, Any] = Field(default_factory=dict)
    debug_meta: dict[str, Any] = Field(default_factory=dict)
