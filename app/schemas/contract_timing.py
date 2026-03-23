"""Step 41 contract timing response schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class DueSoonItem(BaseModel):
    key: str
    type: str
    family: str
    amount_xgp: float
    due_on_day: int
    days_away: int
    income_flag: bool
    status: str


class PlayerContractScheduleResponse(BaseModel):
    player_id: str
    day: int
    active_contract_count: int
    total_due_7d_xgp: float
    clustering_label: str
    next_major_due_on: int | None
    next_major_due_type: str | None
    days_to_next_major_due: int | None
    next_income_on: int | None
    next_income_type: str | None
    days_to_next_income: int | None
    contract_density_score: float
    timing_stability_score: float
    cash_gap_before_next_income_xgp: float
    timing_pressure_label: str
    bridge_need_label: str
    obligation_collision_label: str
    false_payday_pressure: bool
    recurring_obligation_map: dict[str, Any] = Field(default_factory=dict)
    income_cadence: dict[str, Any] = Field(default_factory=dict)
    due_window: dict[str, Any] = Field(default_factory=dict)


class UpcomingObligationWindowResponse(BaseModel):
    player_id: str
    day: int
    due_today: list[dict[str, Any]] = Field(default_factory=list)
    due_in_3d: list[dict[str, Any]] = Field(default_factory=list)
    due_in_7d: list[dict[str, Any]] = Field(default_factory=list)
    outflows_due_today_xgp: float
    outflows_due_3d_xgp: float
    outflows_due_7d_xgp: float
    inflows_expected_7d_xgp: float
    net_7d_xgp: float


class CashTimingPressureStateResponse(BaseModel):
    player_id: str
    day: int
    cash_on_hand_xgp: float
    cash_gap_before_next_income_xgp: float
    contract_density_score: float
    timing_stability_score: float
    timing_pressure_label: str
    clustering_label: str
    bridge_need_label: str
    obligation_collision_label: str
    false_payday_pressure: bool
    next_income_on: int | None
    next_income_type: str | None
    days_to_next_income: int | None
    next_major_due_on: int | None
    next_major_due_type: str | None
    days_to_next_major_due: int | None


class DueSoonSummaryResponse(BaseModel):
    player_id: str
    day: int
    cash_on_hand_xgp: float
    total_due_7d_xgp: float
    total_income_expected_7d_xgp: float
    projected_net_xgp: float
    item_count: int
    items: list[DueSoonItem] = Field(default_factory=list)


class ContractPressureSummaryResponse(BaseModel):
    player_id: str
    day: int
    # timing pressure
    timing_pressure_label: str
    clustering_label: str
    bridge_need_label: str
    obligation_collision_label: str
    contract_density_score: float
    timing_stability_score: float
    false_payday_pressure: bool
    # cash position
    cash_on_hand_xgp: float
    cash_gap_before_next_income_xgp: float
    # upcoming window
    outflows_due_today_xgp: float
    outflows_due_3d_xgp: float
    outflows_due_7d_xgp: float
    inflows_expected_7d_xgp: float
    net_7d_xgp: float
    # income timing
    next_income_on: int | None
    next_income_type: str | None
    days_to_next_income: int | None
    # next major obligation
    next_major_due_on: int | None
    next_major_due_type: str | None
    days_to_next_major_due: int | None
    # risk signals
    late_event_count: int
    delinquency_stage: str
    bridge_borrow_is_rational: bool
    due_soon_items: list[DueSoonItem] = Field(default_factory=list)
