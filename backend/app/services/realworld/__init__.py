"""Real-World Event Pipeline (Phase 3-B-1).

Read-only ingestion of public economic data (FRED) plus a deterministic
rule-based generator that turns observations into DailyEconomyEvent rows.
No LLM calls, no paid sources — that's Phase 3-B-2.
"""

from app.services.realworld.fred_client import FredClient, FredObservation
from app.services.realworld.fred_series import FredSeries
from app.services.realworld.rule_generator import RealWorldEvent, RuleBasedEventGenerator

__all__ = [
    "FredClient",
    "FredObservation",
    "FredSeries",
    "RealWorldEvent",
    "RuleBasedEventGenerator",
]
