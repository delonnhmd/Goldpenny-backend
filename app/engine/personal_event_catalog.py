"""Step 35 personal life-event catalog (bounded, condition-driven templates)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class PersonalLifeEventTemplate:
    """Single personal life-event template used by deterministic shock rolls."""

    event_key: str
    event_family: str
    headline: str
    trigger_tags: tuple[str, ...]
    severity_band: str  # light | moderate | heavy
    cash_impact_range: tuple[float, float] = (0.0, 0.0)
    stress_impact_range: tuple[float, float] = (0.0, 0.0)
    health_impact_range: tuple[float, float] = (0.0, 0.0)
    time_impact_range: tuple[float, float] = (0.0, 0.0)
    work_income_impact_range: tuple[float, float] = (0.0, 0.0)
    business_impact_range: tuple[float, float] = (0.0, 0.0)
    side_income_impact_range: tuple[float, float] = (0.0, 0.0)
    duration_days: int = 0
    recovery_hint: str = ""
    debug_meta: dict[str, object] = field(default_factory=dict)


def _event(
    event_key: str,
    event_family: str,
    headline: str,
    trigger_tags: tuple[str, ...],
    severity_band: str,
    *,
    cash_impact_range: tuple[float, float] = (0.0, 0.0),
    stress_impact_range: tuple[float, float] = (0.0, 0.0),
    health_impact_range: tuple[float, float] = (0.0, 0.0),
    time_impact_range: tuple[float, float] = (0.0, 0.0),
    work_income_impact_range: tuple[float, float] = (0.0, 0.0),
    business_impact_range: tuple[float, float] = (0.0, 0.0),
    side_income_impact_range: tuple[float, float] = (0.0, 0.0),
    duration_days: int = 0,
    recovery_hint: str = "",
) -> PersonalLifeEventTemplate:
    return PersonalLifeEventTemplate(
        event_key=event_key,
        event_family=event_family,
        headline=headline,
        trigger_tags=trigger_tags,
        severity_band=severity_band,
        cash_impact_range=cash_impact_range,
        stress_impact_range=stress_impact_range,
        health_impact_range=health_impact_range,
        time_impact_range=time_impact_range,
        work_income_impact_range=work_income_impact_range,
        business_impact_range=business_impact_range,
        side_income_impact_range=side_income_impact_range,
        duration_days=max(0, int(duration_days)),
        recovery_hint=recovery_hint,
        debug_meta={"catalog_version": "step35_v1"},
    )


PERSONAL_EVENT_CATALOG: tuple[PersonalLifeEventTemplate, ...] = (
    # Financial shocks
    _event(
        "car_repair",
        "financial_shock",
        "Your vehicle needs an unplanned repair.",
        ("high_commute", "job_delivery", "car_mode", "low_cash_buffer"),
        "moderate",
        cash_impact_range=(-160.0, -70.0),
        stress_impact_range=(4.0, 9.0),
        time_impact_range=(0.4, 1.2),
        work_income_impact_range=(-0.12, -0.04),
        side_income_impact_range=(-0.16, -0.06),
        duration_days=3,
        recovery_hint="Reduce optional spend and prioritize schedule recovery.",
    ),
    _event(
        "home_maintenance",
        "financial_shock",
        "A home maintenance issue needs immediate payment.",
        ("housing_burden_high", "low_cash_buffer"),
        "light",
        cash_impact_range=(-90.0, -30.0),
        stress_impact_range=(2.0, 6.0),
        duration_days=2,
        recovery_hint="Pause non-essential upgrades for a day or two.",
    ),
    _event(
        "unexpected_bill",
        "financial_shock",
        "An unexpected bill hits your budget this week.",
        ("low_cash_buffer", "high_debt", "distress_high"),
        "moderate",
        cash_impact_range=(-130.0, -45.0),
        stress_impact_range=(3.0, 8.0),
        duration_days=3,
        recovery_hint="Keep debt control and cash buffer as the short-term focus.",
    ),
    _event(
        "business_inventory_loss",
        "financial_shock",
        "Part of your business inventory gets spoiled or lost.",
        ("has_business", "has_fruit_shop", "supply_pressure"),
        "moderate",
        cash_impact_range=(-80.0, -25.0),
        stress_impact_range=(2.0, 6.0),
        business_impact_range=(-0.15, -0.05),
        duration_days=2,
        recovery_hint="Run conservative inventory until conditions normalize.",
    ),
    _event(
        "shortfall_fee",
        "financial_shock",
        "A short cash shortfall triggers a fee.",
        ("high_debt", "low_cash_buffer"),
        "light",
        cash_impact_range=(-45.0, -12.0),
        stress_impact_range=(1.0, 4.0),
        duration_days=1,
        recovery_hint="Hold a slightly larger cash cushion before growth spending.",
    ),
    # Health / stress shocks
    _event(
        "fatigue_day",
        "health_stress_shock",
        "You hit a fatigue wall and performance dips.",
        ("high_stress", "low_sleep", "overtime"),
        "light",
        stress_impact_range=(2.0, 5.0),
        health_impact_range=(-2.0, -0.5),
        time_impact_range=(0.3, 0.8),
        work_income_impact_range=(-0.10, -0.03),
        duration_days=2,
        recovery_hint="Use a recovery action and protect sleep tonight.",
    ),
    _event(
        "minor_illness",
        "health_stress_shock",
        "A minor illness slows your day.",
        ("low_health", "high_stress", "high_commute"),
        "moderate",
        cash_impact_range=(-35.0, -10.0),
        stress_impact_range=(3.0, 8.0),
        health_impact_range=(-5.0, -2.0),
        time_impact_range=(0.5, 1.5),
        work_income_impact_range=(-0.16, -0.06),
        duration_days=3,
        recovery_hint="Prioritize lower strain actions until health stabilizes.",
    ),
    _event(
        "stress_spike",
        "health_stress_shock",
        "A stress spike makes focus and patience harder today.",
        ("high_stress", "distress_high", "high_commute"),
        "light",
        stress_impact_range=(4.0, 9.0),
        health_impact_range=(-2.0, -0.5),
        work_income_impact_range=(-0.08, -0.03),
        business_impact_range=(-0.08, -0.02),
        duration_days=2,
        recovery_hint="Take a lighter plan block and avoid stacking pressure.",
    ),
    _event(
        "burnout_warning",
        "health_stress_shock",
        "Burnout warning: your pace is becoming unsustainable.",
        ("burnout_risk_high", "overtime", "low_sleep"),
        "heavy",
        stress_impact_range=(8.0, 15.0),
        health_impact_range=(-7.0, -3.0),
        time_impact_range=(1.0, 2.5),
        work_income_impact_range=(-0.22, -0.10),
        business_impact_range=(-0.18, -0.08),
        side_income_impact_range=(-0.20, -0.10),
        duration_days=4,
        recovery_hint="Shift to a recovery-first window for several days.",
    ),
    # Work disruptions
    _event(
        "reduced_hours",
        "work_disruption",
        "This week brings reduced hours at work.",
        ("job_retail", "job_service", "confidence_weak"),
        "moderate",
        stress_impact_range=(2.0, 7.0),
        work_income_impact_range=(-0.18, -0.08),
        duration_days=3,
        recovery_hint="Use supplemental income carefully without overloading stress.",
    ),
    _event(
        "delayed_bonus",
        "work_disruption",
        "A bonus or expected payout is delayed.",
        ("job_banker", "career_push"),
        "light",
        cash_impact_range=(-40.0, -10.0),
        stress_impact_range=(1.0, 4.0),
        duration_days=2,
        recovery_hint="Delay optional spending until cash timing improves.",
    ),
    _event(
        "performance_pressure_week",
        "work_disruption",
        "Work pressure increases and mistakes become costlier.",
        ("job_banker", "job_chef", "high_stress"),
        "moderate",
        stress_impact_range=(3.0, 8.0),
        health_impact_range=(-3.0, -1.0),
        work_income_impact_range=(-0.10, -0.04),
        duration_days=3,
        recovery_hint="Mix high-focus work with recovery to preserve output quality.",
    ),
    _event(
        "vehicle_issue_shift_loss",
        "work_disruption",
        "Vehicle trouble causes a missed shift window.",
        ("job_delivery", "car_mode", "high_commute"),
        "moderate",
        cash_impact_range=(-60.0, -18.0),
        stress_impact_range=(3.0, 7.0),
        time_impact_range=(0.6, 1.6),
        work_income_impact_range=(-0.20, -0.08),
        side_income_impact_range=(-0.22, -0.10),
        duration_days=2,
        recovery_hint="Stabilize transport reliability before heavy grind days.",
    ),
    # Opportunity events
    _event(
        "overtime_chance",
        "opportunity",
        "An overtime window opens up this cycle.",
        ("job_chef", "job_mechanic", "job_aircraft_mechanic", "opportunity_density_high"),
        "light",
        cash_impact_range=(18.0, 55.0),
        stress_impact_range=(1.0, 4.0),
        time_impact_range=(0.4, 1.2),
        work_income_impact_range=(0.05, 0.15),
        duration_days=1,
        recovery_hint="Use overtime selectively to avoid follow-on fatigue.",
    ),
    _event(
        "side_gig_chance",
        "opportunity",
        "A short side gig appears with decent pay.",
        ("high_opportunity_region", "side_income_ready"),
        "light",
        cash_impact_range=(12.0, 42.0),
        stress_impact_range=(0.5, 3.0),
        time_impact_range=(0.3, 0.9),
        side_income_impact_range=(0.06, 0.18),
        duration_days=1,
        recovery_hint="Take it if stress is controlled and debt pressure is active.",
    ),
    _event(
        "temporary_demand_spike",
        "opportunity",
        "Local demand spikes and your business can capture extra flow.",
        ("has_business", "opportunity_density_high"),
        "moderate",
        cash_impact_range=(15.0, 75.0),
        stress_impact_range=(1.0, 4.0),
        business_impact_range=(0.08, 0.22),
        duration_days=2,
        recovery_hint="Use demand spike carefully; avoid over-restocking into risk.",
    ),
    _event(
        "supplier_discount",
        "opportunity",
        "A supplier discount window improves your unit economics.",
        ("has_fruit_shop", "has_food_truck"),
        "light",
        cash_impact_range=(8.0, 36.0),
        business_impact_range=(0.06, 0.18),
        duration_days=2,
        recovery_hint="Convert discount gains into buffer, not just expansion.",
    ),
    _event(
        "networking_break",
        "opportunity",
        "A useful networking break improves near-term work momentum.",
        ("networking_high", "job_banker", "career_builder"),
        "light",
        cash_impact_range=(10.0, 32.0),
        stress_impact_range=(-3.0, -1.0),
        work_income_impact_range=(0.04, 0.12),
        duration_days=2,
        recovery_hint="Lean into career actions while momentum is favorable.",
    ),
    # Recovery/support events
    _event(
        "expense_delay_relief",
        "recovery_support",
        "A payment or expense gets delayed, easing this week's pressure.",
        ("low_cash_buffer", "distress_high"),
        "light",
        cash_impact_range=(15.0, 55.0),
        stress_impact_range=(-4.0, -1.0),
        duration_days=2,
        recovery_hint="Use relief to rebuild cushion instead of new obligations.",
    ),
    _event(
        "health_rebound",
        "recovery_support",
        "You recover better than expected and feel more stable.",
        ("high_stress", "low_health", "recovery_actions"),
        "light",
        stress_impact_range=(-5.0, -2.0),
        health_impact_range=(1.5, 4.5),
        work_income_impact_range=(0.02, 0.08),
        duration_days=2,
        recovery_hint="Keep recovery cadence so gains are not lost immediately.",
    ),
    _event(
        "lower_commute_week",
        "recovery_support",
        "Commute friction eases for a short window.",
        ("high_commute", "move_or_rent_closer_recent"),
        "light",
        stress_impact_range=(-3.0, -1.0),
        time_impact_range=(-0.8, -0.3),
        work_income_impact_range=(0.02, 0.07),
        duration_days=2,
        recovery_hint="Use regained time for stability and planning.",
    ),
    _event(
        "better_week_at_work",
        "recovery_support",
        "Work week smooths out with fewer disruptions.",
        ("job_stable", "stress_moderate"),
        "moderate",
        cash_impact_range=(12.0, 46.0),
        stress_impact_range=(-4.0, -1.5),
        work_income_impact_range=(0.04, 0.11),
        duration_days=3,
        recovery_hint="Convert smoother week into stronger debt/cash position.",
    ),
)


EVENT_BY_KEY: dict[str, PersonalLifeEventTemplate] = {
    item.event_key: item for item in PERSONAL_EVENT_CATALOG
}

