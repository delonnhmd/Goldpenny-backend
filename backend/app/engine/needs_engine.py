"""
Needs Engine — daily basket consumption quality evaluation for Step 6.

Design principles:
  - All functions are pure and stateless.  Same inputs → same outputs.
  - No randomness anywhere.  Results are fully deterministic.
  - No DB access.  All DB-facing logic lives in daily_engine.py.
  - No nutrition simulation: this is a basket-category quality model, not a
    calorie/macro tracker.  The 4 basket categories serve as lifestyle proxies.
  - Effects are intentionally modest — this is an MVP quality layer, not a
    hardcore survival sim.

Economic / lifestyle intent:
  Daily basket spending now affects personal wellbeing at settlement.
  This is a quality-of-life layer built on top of the expense system.

  The needs evaluation creates a real loop:
    Work → Earn XGP → Buy Baskets → End Day →
    Needs Quality Evaluated → Health/Stress Outcome Changes →
    Next Day Feels Different

  Without this, baskets are only expense categories.
  With this, they become lifestyle decisions.

  Sample flows (documented here for reference):
    Day 7:
      - Player works and earns XGP.
      - Player buys only convenience basket.
      - Settlement evaluates "weak" daily needs quality.
      - Player gets less recovery and a small stress penalty.
      - Next day starts in worse condition than a balanced buyer.

    Day 8:
      - Player buys essentials + protein + produce.
      - Settlement evaluates "good" daily needs quality.
      - Player gets slightly better recovery.
      - Next day starts in better shape.

Tier system:
  poor      needs_score < 0.75
  weak      0.75 <= needs_score < 1.25
  adequate  1.25 <= needs_score < 1.75
  good      1.75 <= needs_score < 2.25
  excellent needs_score >= 2.25

Modifier rules (applied on top of base settlement recovery):
  poor:      stress_penalty +4, health -1, food_quality_modifier -2
  weak:      stress_penalty +2, health  0, food_quality_modifier -1
  adequate:  stress_penalty  0, health  0, food_quality_modifier  0
  good:      stress_penalty -1, health +1, food_quality_modifier +1
  excellent: stress_penalty -2, health +1, food_quality_modifier +2

  Note: negative stress_penalty means bonus stress relief (better than base).
"""

from __future__ import annotations

# ─────────────────────────────────────────────────────────────────────────────
# Tier boundaries
# ─────────────────────────────────────────────────────────────────────────────

TIER_THRESHOLDS: list[tuple[float, str]] = [
    (2.25, "excellent"),
    (1.75, "good"),
    (1.25, "adequate"),
    (0.75, "weak"),
    (0.0,  "poor"),
]


# ─────────────────────────────────────────────────────────────────────────────
# Pure helper functions
# ─────────────────────────────────────────────────────────────────────────────


def normalize_daily_basket_units(
    essentials_units: float,
    protein_units: float,
    produce_units: float,
    convenience_units: float,
) -> dict:
    """
    Clamp all basket unit values to >= 0 and return a normalized dict.

    Negative values can theoretically arrive from bad data or refund logic.
    This function ensures downstream calculations never operate on negatives.
    """
    return {
        "essentials":   max(0.0, float(essentials_units)),
        "protein":      max(0.0, float(protein_units)),
        "produce":      max(0.0, float(produce_units)),
        "convenience":  max(0.0, float(convenience_units)),
    }


def calculate_survival_coverage_score(
    essentials_units: float,
    protein_units: float,
    produce_units: float,
    convenience_units: float,
) -> float:
    """
    Measure whether the player covered basic daily living needs today.

    Essentials matter most — they represent the core food/household staples
    every person needs.  Protein and produce provide supplementary support.
    Convenience contributes only weakly because it is low-quality coverage.

    Formula:
        coverage = min(essentials, 2) * 0.45
                 + min(protein, 2)    * 0.25
                 + min(produce, 2)    * 0.20
                 + min(convenience, 2)* 0.10

    Maximum score ≈ 2.0 (when all 4 are bought at ≥ 2 units each).
    A player who only buys convenience maxes at 0.20 — survival is covered
    weakly, which translates to "weak" or "poor" tier depending on amount.

    Deterministic only.
    """
    units = normalize_daily_basket_units(
        essentials_units, protein_units, produce_units, convenience_units
    )
    coverage = (
        min(units["essentials"],  2.0) * 0.45
        + min(units["protein"],   2.0) * 0.25
        + min(units["produce"],   2.0) * 0.20
        + min(units["convenience"], 2.0) * 0.10
    )
    return round(coverage, 4)


def calculate_food_quality_score(
    essentials_units: float,
    protein_units: float,
    produce_units: float,
    convenience_units: float,
) -> float:
    """
    Measure the quality of the basket mix, not just raw coverage.

    Protein and produce are highest quality — they provide nutritious variety.
    Essentials are neutral-positive — reliable but not nutrient-rich alone.
    Convenience reduces quality if overused (> 1 unit/day) — fast food
    pressure on recovery quality.

    Formula:
        quality = essentials   * 0.20
                + protein      * 0.35
                + produce      * 0.35
                - max(0, convenience - 1.0) * 0.20

    Clamped to [0, 2.5].

    A player buying 2 essentials + 2 protein + 2 produce with no convenience
    gets: 0.40 + 0.70 + 0.70 = 1.80.

    A player buying 3 convenience only gets: 0 + 0 + 0 - max(0, 3-1)*0.20
    = -0.40 → clamped to 0.

    Deterministic only.
    """
    units = normalize_daily_basket_units(
        essentials_units, protein_units, produce_units, convenience_units
    )
    raw = (
        units["essentials"]  * 0.20
        + units["protein"]   * 0.35
        + units["produce"]   * 0.35
        - max(0.0, units["convenience"] - 1.0) * 0.20
    )
    return round(max(0.0, min(2.5, raw)), 4)


def _resolve_tier(needs_score: float) -> str:
    """Return the needs tier string for the given score."""
    for threshold, tier in TIER_THRESHOLDS:
        if needs_score >= threshold:
            return tier
    return "poor"  # fallback (score below 0.0, e.g. exactly 0)


def calculate_daily_needs_score(
    essentials_units: float,
    protein_units: float,
    produce_units: float,
    convenience_units: float,
) -> dict:
    """
    Produce a complete daily needs evaluation result.

    Combines survival coverage (65% weight) and food quality (35% weight) into
    a single needs_score.  Assigns a tier label based on that score.

    Formula:
        needs_score = survival_coverage_score * 0.65
                    + food_quality_score       * 0.35

    Returned dict keys:
        survival_coverage_score  (float)
        food_quality_score       (float)
        needs_score              (float)
        needs_tier               (str)

    Safe for zero-purchase days: all scores will be 0.0 and tier will be "poor".
    This is intentional — skipping needs should cause pressure.

    Deterministic only.
    """
    survival_coverage = calculate_survival_coverage_score(
        essentials_units, protein_units, produce_units, convenience_units
    )
    food_quality = calculate_food_quality_score(
        essentials_units, protein_units, produce_units, convenience_units
    )
    needs_score = round(
        survival_coverage * 0.65 + food_quality * 0.35,
        4,
    )
    tier = _resolve_tier(needs_score)

    return {
        "survival_coverage_score": survival_coverage,
        "food_quality_score":      food_quality,
        "needs_score":             needs_score,
        "needs_tier":              tier,
    }


def calculate_needs_based_settlement_modifiers(
    needs_tier: str,
    needs_score: float,
) -> dict:
    """
    Convert a daily needs tier into concrete health/stress settlement modifiers.

    Returned dict keys:
        stress_penalty_from_needs  (int)
            Positive = extra stress added on top of base recovery.
            Negative = bonus stress relief beyond base recovery.
        health_modifier_from_needs (int)
            Positive = extra health gain.
            Negative = health loss on top of base health calculation.
        food_quality_modifier      (int)
            Summary signal (not directly applied to stats) — useful for
            frontend display to explain why recovery was better or worse.

    Rules:
        poor      stress +4, health -1, food_quality -2   (skipping basics hurts)
        weak      stress +2, health  0, food_quality -1   (convenience-only mediocre)
        adequate  stress  0, health  0, food_quality  0   (neutral, no bonus/penalty)
        good      stress -1, health +1, food_quality +1   (balanced diet helps)
        excellent stress -2, health +1, food_quality +2   (best possible recovery boost)

    Effects are intentionally modest.  This is not a hardcore survival system.
    Basket choices now matter economically and biologically, but one bad day
    will not destroy a player.
    """
    MODIFIER_TABLE: dict[str, dict] = {
        "poor":      {"stress_penalty_from_needs":  4, "health_modifier_from_needs": -1, "food_quality_modifier": -2},
        "weak":      {"stress_penalty_from_needs":  2, "health_modifier_from_needs":  0, "food_quality_modifier": -1},
        "adequate":  {"stress_penalty_from_needs":  0, "health_modifier_from_needs":  0, "food_quality_modifier":  0},
        "good":      {"stress_penalty_from_needs": -1, "health_modifier_from_needs":  1, "food_quality_modifier":  1},
        "excellent": {"stress_penalty_from_needs": -2, "health_modifier_from_needs":  1, "food_quality_modifier":  2},
    }
    return MODIFIER_TABLE.get(needs_tier, MODIFIER_TABLE["poor"]).copy()


def build_needs_summary(
    essentials_units: float,
    protein_units: float,
    produce_units: float,
    convenience_units: float,
    needs_result: dict,
    modifiers: dict,
) -> dict:
    """
    Build a JSON-friendly summary payload for storage in the settlement log.

    This dict is stored inside summary_json and lets the frontend explain why
    settlement was better or worse on any given day.

    Keys:
        basket_units             — raw daily units per category
        survival_coverage_score  — how well basics were covered
        food_quality_score       — how nutritious the mix was
        needs_score              — combined score
        needs_tier               — tier label
        stress_penalty_from_needs
        health_modifier_from_needs
        food_quality_modifier
    """
    return {
        "basket_units": {
            "essentials":  round(float(essentials_units), 4),
            "protein":     round(float(protein_units), 4),
            "produce":     round(float(produce_units), 4),
            "convenience": round(float(convenience_units), 4),
        },
        "survival_coverage_score":  needs_result.get("survival_coverage_score", 0.0),
        "food_quality_score":       needs_result.get("food_quality_score", 0.0),
        "needs_score":              needs_result.get("needs_score", 0.0),
        "needs_tier":               needs_result.get("needs_tier", "poor"),
        "stress_penalty_from_needs":   modifiers.get("stress_penalty_from_needs", 0),
        "health_modifier_from_needs":  modifiers.get("health_modifier_from_needs", 0),
        "food_quality_modifier":       modifiers.get("food_quality_modifier", 0),
    }
