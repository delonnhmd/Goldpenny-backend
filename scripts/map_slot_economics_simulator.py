from __future__ import annotations

from dataclasses import dataclass


DISTRICT_DEFAULTS = {
    "downtown": {"demand": 78, "traffic": 84, "competition": 72, "risk": 62, "supply": 66, "fit": "food_truck"},
    "suburban": {"demand": 58, "traffic": 54, "competition": 34, "risk": 24, "supply": 78, "fit": "fruit_shop"},
    "market": {"demand": 82, "traffic": 78, "competition": 76, "risk": 46, "supply": 82, "fit": "either"},
    "industrial": {"demand": 42, "traffic": 48, "competition": 32, "risk": 38, "supply": 88, "fit": "food_truck"},
}

DISTRICT_GROWTH = {
    "downtown": 0.12,
    "market": 0.10,
    "industrial": 0.08,
    "suburban": 0.05,
}

ADDRESS_POOLS = {
    "downtown": [
        "1203 Market Line Ave",
        "88 Riverfront Plaza",
        "410 Central Trade St",
        "726 Commerce Row",
        "51 Skyline Market Blvd",
    ],
    "suburban": [
        "240 Oak Garden Ln",
        "715 Greenfield Way",
        "332 Maple Creek Dr",
        "909 Willow Bend Rd",
        "128 Pine Orchard St",
    ],
    "market": [
        "200 Vendor Square",
        "415 Fresh Market St",
        "909 Orchard Plaza",
        "77 Trade Corner",
    ],
    "industrial": [
        "600 Foundry Loop",
        "144 Warehouse Park Dr",
        "915 Rail Yard Ave",
    ],
}

SLOT_TYPE_BONUSES = {
    "commercial_core": {"demand": 8, "traffic": 6, "competition": 8, "risk": 4, "supply": 2},
    "mixed_use": {"demand": 5, "traffic": 4, "competition": 3, "risk": 2, "supply": 4},
    "service_flex": {"demand": 2, "traffic": 3, "competition": 1, "risk": 1, "supply": 8},
    "logistics": {"demand": -4, "traffic": 1, "competition": -4, "risk": 2, "supply": 12},
    "residential_edge": {"demand": 3, "traffic": -2, "competition": -5, "risk": -6, "supply": 6},
}

BASE_REVENUE = {"fruit_shop": 120.0, "food_truck": 180.0}


@dataclass
class SlotSeed:
    slot_id: str
    district: str
    slot_type: str
    purchase_price: float
    traffic_score: float
    development_potential: float


def stable_hash(value: str) -> int:
    hashed = 0
    for char in value:
        hashed = ((hashed << 5) - hashed) + ord(char)
        hashed &= 0xFFFFFFFF
    return abs(hashed)


def clamp(value: float, minimum: float, maximum: float) -> float:
    return min(maximum, max(minimum, value))


def money(value: float) -> float:
    return round(value + 1e-9, 2)


def zone_bonus(slot_type: str) -> dict[str, float]:
    return SLOT_TYPE_BONUSES.get(slot_type, {"demand": 0, "traffic": 0, "competition": 0, "risk": 0, "supply": 0})


def stable_address(slot_id: str, district: str) -> str:
    pool = ADDRESS_POOLS[district]
    return pool[stable_hash(f"{district}:{slot_id}") % len(pool)]


def slot_record(seed: SlotSeed) -> dict[str, float | str]:
    defaults = DISTRICT_DEFAULTS[seed.district]
    bonus = zone_bonus(seed.slot_type)
    traffic = round(clamp((defaults["traffic"] * 0.42) + (seed.traffic_score * 0.58) + bonus["traffic"], 0, 100))
    demand = round(clamp((defaults["demand"] * 0.38) + (seed.development_potential * 0.34) + (traffic * 0.28) + bonus["demand"], 0, 100))
    competition = round(clamp((defaults["competition"] * 0.62) + (traffic * 0.2) + (demand * 0.18) + bonus["competition"], 0, 100))
    risk = round(clamp((defaults["risk"] * 0.72) + (competition * 0.16) + (max(0, traffic - 50) * 0.12) + bonus["risk"], 0, 100))
    supply = round(clamp((defaults["supply"] * 0.66) + (seed.development_potential * 0.12) + bonus["supply"], 0, 100))
    value = seed.purchase_price * (
        1
        + ((demand - 50) / 250)
        + ((traffic - 50) / 300)
        - (risk / 500)
        + DISTRICT_GROWTH[seed.district]
    )
    current_value = money(clamp(value, seed.purchase_price * 0.75, seed.purchase_price * 1.75))
    return {
        "slot_id": seed.slot_id,
        "address": stable_address(seed.slot_id, seed.district),
        "district": seed.district,
        "slot_type": seed.slot_type,
        "purchase_price": seed.purchase_price,
        "current_value": current_value,
        "demand_score": demand,
        "foot_traffic_score": traffic,
        "competition_score": competition,
        "risk_score": risk,
        "supply_access_score": supply,
        "best_business_fit": defaults["fit"],
    }


def revenue_preview(slot: dict[str, float | str], business_type: str) -> tuple[float, float]:
    multiplier = clamp(
        1
        + ((slot["demand_score"] - 50) / 200)
        + ((slot["foot_traffic_score"] - 50) / 180)
        - ((slot["competition_score"] - 50) / 220)
        - ((slot["risk_score"] - 50) / 300)
        + ((slot["supply_access_score"] - 50) / 250),
        0.55,
        1.75,
    )
    expected = BASE_REVENUE[business_type] * multiplier
    return money(expected * 0.75), money(expected * 1.25)


def main() -> None:
    seeds = [
        SlotSeed("downtown_exchange:exchange_lot_01", "downtown", "mixed_use", 360, 72, 82),
        SlotSeed("downtown_exchange:exchange_lot_07", "downtown", "commercial_core", 470, 84, 92),
        SlotSeed("downtown_exchange:exchange_lot_16", "downtown", "commercial_core", 506, 86, 93),
        SlotSeed("suburban_brookside:brook_lot_07", "suburban", "residential_edge", 248, 48, 72),
        SlotSeed("suburban_brookside:brook_lot_11", "suburban", "mixed_use", 260, 56, 75),
        SlotSeed("suburban_brookside:brook_lot_16", "suburban", "mixed_use", 292, 65, 82),
        SlotSeed("market_row:market_lot_01", "market", "mixed_use", 335, 74, 84),
        SlotSeed("market_row:market_lot_02", "market", "commercial_core", 388, 80, 88),
        SlotSeed("harbor_works:harbor_lot_03", "industrial", "service_flex", 370, 76, 86),
        SlotSeed("harbor_works:harbor_lot_09", "industrial", "logistics", 452, 86, 90),
    ]

    print("Gold Penny map slot economics simulator\n")
    for seed in seeds:
        slot = slot_record(seed)
        fruit_low, fruit_high = revenue_preview(slot, "fruit_shop")
        food_low, food_high = revenue_preview(slot, "food_truck")
        print(f"{slot['address']} [{slot['district']}]")
        print(
            f"  purchase ${money(slot['purchase_price'])} | current ${slot['current_value']} | "
            f"demand {slot['demand_score']} | traffic {slot['foot_traffic_score']} | "
            f"competition {slot['competition_score']} | risk {slot['risk_score']} | "
            f"best fit {slot['best_business_fit']}"
        )
        print(
            f"  fruit shop range ${fruit_low} - ${fruit_high} | "
            f"food truck range ${food_low} - ${food_high}\n"
        )


if __name__ == "__main__":
    main()
