from __future__ import annotations

from decimal import Decimal

from app.models.enums import BasketType


SUPPLIER_ITEM_CATALOG: dict[str, dict[str, object]] = {
    "mango": {
        "item_id": "mango",
        "display_name": "Mango",
        "compatible_business_type": "fruit_shop",
        "basket_link": BasketType.produce,
        "base_wholesale_cost": Decimal("1.25"),
        "suggested_retail_price": Decimal("2.40"),
        "spoilage_rate": Decimal("0.11"),
        "demand_weight": Decimal("1.16"),
        "unit_label": "crate",
    },
    "orange": {
        "item_id": "orange",
        "display_name": "Orange",
        "compatible_business_type": "fruit_shop",
        "basket_link": BasketType.produce,
        "base_wholesale_cost": Decimal("0.85"),
        "suggested_retail_price": Decimal("1.75"),
        "spoilage_rate": Decimal("0.06"),
        "demand_weight": Decimal("1.05"),
        "unit_label": "crate",
    },
    "apple": {
        "item_id": "apple",
        "display_name": "Apple",
        "compatible_business_type": "fruit_shop",
        "basket_link": BasketType.produce,
        "base_wholesale_cost": Decimal("0.75"),
        "suggested_retail_price": Decimal("1.60"),
        "spoilage_rate": Decimal("0.04"),
        "demand_weight": Decimal("1.00"),
        "unit_label": "crate",
    },
    "grape": {
        "item_id": "grape",
        "display_name": "Grape",
        "compatible_business_type": "fruit_shop",
        "basket_link": BasketType.produce,
        "base_wholesale_cost": Decimal("1.10"),
        "suggested_retail_price": Decimal("2.10"),
        "spoilage_rate": Decimal("0.07"),
        "demand_weight": Decimal("1.08"),
        "unit_label": "box",
    },
    "banana": {
        "item_id": "banana",
        "display_name": "Banana",
        "compatible_business_type": "fruit_shop",
        "basket_link": BasketType.produce,
        "base_wholesale_cost": Decimal("0.55"),
        "suggested_retail_price": Decimal("1.25"),
        "spoilage_rate": Decimal("0.09"),
        "demand_weight": Decimal("1.12"),
        "unit_label": "bundle",
    },
    "strawberry": {
        "item_id": "strawberry",
        "display_name": "Strawberry",
        "compatible_business_type": "fruit_shop",
        "basket_link": BasketType.produce,
        "base_wholesale_cost": Decimal("1.45"),
        "suggested_retail_price": Decimal("2.75"),
        "spoilage_rate": Decimal("0.14"),
        "demand_weight": Decimal("1.20"),
        "unit_label": "tray",
    },
    "bread": {
        "item_id": "bread",
        "display_name": "Bread",
        "compatible_business_type": "food_truck",
        "basket_link": BasketType.essentials,
        "base_wholesale_cost": Decimal("0.48"),
        "suggested_retail_price": Decimal("1.20"),
        "spoilage_rate": Decimal("0.05"),
        "demand_weight": Decimal("1.00"),
        "unit_label": "pack",
    },
    "rice": {
        "item_id": "rice",
        "display_name": "Rice",
        "compatible_business_type": "food_truck",
        "basket_link": BasketType.essentials,
        "base_wholesale_cost": Decimal("0.36"),
        "suggested_retail_price": Decimal("1.10"),
        "spoilage_rate": Decimal("0.03"),
        "demand_weight": Decimal("0.95"),
        "unit_label": "bag",
    },
    "chicken": {
        "item_id": "chicken",
        "display_name": "Chicken",
        "compatible_business_type": "food_truck",
        "basket_link": BasketType.protein,
        "base_wholesale_cost": Decimal("1.35"),
        "suggested_retail_price": Decimal("3.00"),
        "spoilage_rate": Decimal("0.07"),
        "demand_weight": Decimal("1.12"),
        "unit_label": "tray",
    },
    "beef": {
        "item_id": "beef",
        "display_name": "Beef",
        "compatible_business_type": "food_truck",
        "basket_link": BasketType.protein,
        "base_wholesale_cost": Decimal("1.95"),
        "suggested_retail_price": Decimal("3.80"),
        "spoilage_rate": Decimal("0.08"),
        "demand_weight": Decimal("1.05"),
        "unit_label": "tray",
    },
    "egg": {
        "item_id": "egg",
        "display_name": "Egg",
        "compatible_business_type": "food_truck",
        "basket_link": BasketType.protein,
        "base_wholesale_cost": Decimal("0.42"),
        "suggested_retail_price": Decimal("1.30"),
        "spoilage_rate": Decimal("0.06"),
        "demand_weight": Decimal("0.98"),
        "unit_label": "dozen",
    },
    "cooking_oil": {
        "item_id": "cooking_oil",
        "display_name": "Cooking Oil",
        "compatible_business_type": "food_truck",
        "basket_link": BasketType.convenience,
        "base_wholesale_cost": Decimal("0.82"),
        "suggested_retail_price": Decimal("1.60"),
        "spoilage_rate": Decimal("0.02"),
        "demand_weight": Decimal("0.72"),
        "unit_label": "bottle",
    },
}


def compatible_business_type(spec: dict[str, object]) -> str:
    return str(spec.get("compatible_business_type") or "").strip().lower()


def supplier_items_for_business_type(business_type: str) -> list[dict[str, object]]:
    normalized = str(business_type or "").strip().lower()
    return [
        spec
        for spec in SUPPLIER_ITEM_CATALOG.values()
        if compatible_business_type(spec) == normalized
    ]
