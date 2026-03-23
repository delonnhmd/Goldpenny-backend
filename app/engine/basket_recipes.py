"""Static basket -> node composition map for the supply-chain compute engine."""

from __future__ import annotations

from decimal import Decimal

RECIPE_SUM_TOLERANCE = Decimal("0.0001")


# Each basket recipe must sum to 1.00 for deterministic weighted aggregation.
BASKET_RECIPES: dict[str, dict[str, Decimal]] = {
    "essentials": {
        "farming": Decimal("0.35"),
        "processing": Decimal("0.30"),
        "trucking": Decimal("0.20"),
        "retail": Decimal("0.15"),
    },
    "protein": {
        "farming": Decimal("0.30"),
        "processing": Decimal("0.30"),
        "trucking": Decimal("0.20"),
        "retail": Decimal("0.10"),
        "utilities": Decimal("0.10"),
    },
    "produce": {
        "farming": Decimal("0.45"),
        "trucking": Decimal("0.25"),
        "retail": Decimal("0.15"),
        "labor": Decimal("0.15"),
    },
    "convenience": {
        "processing": Decimal("0.35"),
        "trucking": Decimal("0.20"),
        "retail": Decimal("0.25"),
        "utilities": Decimal("0.20"),
    },
}


def validate_basket_recipes() -> None:
    """Fail fast if any static basket recipe does not sum to 1.00."""
    for basket_key, recipe in BASKET_RECIPES.items():
        total = sum(recipe.values(), Decimal("0"))
        if abs(total - Decimal("1.00")) > RECIPE_SUM_TOLERANCE:
            raise ValueError(
                f"Basket recipe weights must sum to 1.00. basket={basket_key} total={total}"
            )


validate_basket_recipes()
