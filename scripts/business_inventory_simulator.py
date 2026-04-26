from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP


MONEY_Q = Decimal("0.01")
UNIT_Q = Decimal("0.0001")

NO_INVENTORY = "No usable inventory. Buy stock before operating."
URGENT = "Urgent: restock before next business day."
LOW = "Low inventory: restock soon."


def money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_Q, rounding=ROUND_HALF_UP)


def unit(value: Decimal) -> Decimal:
    return value.quantize(UNIT_Q, rounding=ROUND_HALF_UP)


def warning(days_left: Decimal, usable_units: Decimal) -> str:
    if usable_units <= 0:
        return NO_INVENTORY
    if days_left <= Decimal("1"):
        return URGENT
    if days_left <= Decimal("3"):
        return LOW
    return "-"


@dataclass
class DailyResult:
    day: int
    revenue: Decimal
    cogs: Decimal
    labor: Decimal
    overhead: Decimal
    fuel: Decimal
    spoilage_units: Decimal
    spoilage_cost: Decimal
    net_profit: Decimal
    inventory_left: Decimal
    days_left: Decimal
    warning: str


def fruit_day(day: int, produce_units: Decimal, demand_units: int) -> tuple[Decimal, DailyResult]:
    labor = Decimal("45.00")
    overhead = Decimal("8.00")
    unit_cost = Decimal("4.00")
    sell_price = Decimal("4.88")

    available_units = max(0, int(produce_units))
    if available_units <= 0:
        result = DailyResult(
            day=day,
            revenue=Decimal("0.00"),
            cogs=Decimal("0.00"),
            labor=Decimal("0.00"),
            overhead=overhead,
            fuel=Decimal("0.00"),
            spoilage_units=Decimal("0.0000"),
            spoilage_cost=Decimal("0.00"),
            net_profit=money(-overhead),
            inventory_left=produce_units,
            days_left=Decimal("0.0000"),
            warning=NO_INVENTORY,
        )
        return produce_units, result

    sold = Decimal(min(demand_units, available_units))
    remaining_after_sales = unit(produce_units - sold)
    spoilage_units = unit(remaining_after_sales * Decimal("0.05"))
    inventory_left = unit(remaining_after_sales - spoilage_units)
    spoilage_cost = money(spoilage_units * unit_cost)
    revenue = money(sold * sell_price)
    cogs = money(sold * unit_cost)
    net_profit = money(revenue - cogs - labor - overhead - spoilage_cost)
    days_left = unit(inventory_left / Decimal("10")) if inventory_left > 0 else Decimal("0.0000")
    result = DailyResult(
        day=day,
        revenue=revenue,
        cogs=cogs,
        labor=labor,
        overhead=overhead,
        fuel=Decimal("0.00"),
        spoilage_units=spoilage_units,
        spoilage_cost=spoilage_cost,
        net_profit=net_profit,
        inventory_left=inventory_left,
        days_left=days_left,
        warning=warning(days_left, inventory_left),
    )
    return inventory_left, result


def truck_day(
    day: int,
    essentials_units: Decimal,
    protein_units: Decimal,
    demand_units: int,
) -> tuple[Decimal, Decimal, DailyResult]:
    labor = Decimal("65.00")
    overhead = Decimal("14.00")
    fuel = Decimal("5.50")
    essentials_unit_cost = Decimal("4.50")
    protein_unit_cost = Decimal("6.60")
    ticket = Decimal("9.15")
    usable_meals = min(essentials_units, protein_units)

    available_meals = max(0, int(usable_meals))
    if available_meals <= 0:
        inventory_left = unit(essentials_units + protein_units)
        result = DailyResult(
            day=day,
            revenue=Decimal("0.00"),
            cogs=Decimal("0.00"),
            labor=Decimal("0.00"),
            overhead=overhead,
            fuel=Decimal("0.00"),
            spoilage_units=Decimal("0.0000"),
            spoilage_cost=Decimal("0.00"),
            net_profit=money(-overhead),
            inventory_left=inventory_left,
            days_left=Decimal("0.0000"),
            warning=NO_INVENTORY,
        )
        return essentials_units, protein_units, result

    sold = Decimal(min(demand_units, available_meals))
    remaining_essentials = unit(essentials_units - sold)
    remaining_protein_before_spoilage = unit(protein_units - sold)
    spoilage_units = unit(remaining_protein_before_spoilage * Decimal("0.03"))
    remaining_protein = unit(remaining_protein_before_spoilage - spoilage_units)
    inventory_left = unit(remaining_essentials + remaining_protein)
    usable_after = min(remaining_essentials, remaining_protein)
    days_left = unit(usable_after / Decimal("12")) if usable_after > 0 else Decimal("0.0000")

    revenue = money(sold * ticket)
    cogs = money((sold * essentials_unit_cost) + (sold * protein_unit_cost))
    spoilage_cost = money(spoilage_units * protein_unit_cost)
    net_profit = money(revenue - cogs - labor - overhead - fuel - spoilage_cost)
    result = DailyResult(
        day=day,
        revenue=revenue,
        cogs=cogs,
        labor=labor,
        overhead=overhead,
        fuel=fuel,
        spoilage_units=spoilage_units,
        spoilage_cost=spoilage_cost,
        net_profit=net_profit,
        inventory_left=inventory_left,
        days_left=days_left,
        warning=warning(days_left, usable_after),
    )
    return remaining_essentials, remaining_protein, result


def print_result(label: str, result: DailyResult) -> None:
    print(
        f"{label} day {result.day}: "
        f"revenue ${result.revenue}, COGS ${result.cogs}, labor ${result.labor}, "
        f"overhead ${result.overhead}, fuel ${result.fuel}, spoilage {result.spoilage_units}u/${result.spoilage_cost}, "
        f"net ${result.net_profit}, inventory left {result.inventory_left}u, "
        f"days left {result.days_left}, warning {result.warning}"
    )


def simulate_fruit_shop() -> None:
    print("\nFruit shop, 5 days")
    produce = Decimal("120")
    for day, demand in enumerate([28, 32, 35, 31, 33], start=1):
        produce, result = fruit_day(day, produce, demand)
        print_result("fruit_shop", result)


def simulate_food_truck() -> None:
    print("\nFood truck, 5 days")
    essentials = Decimal("95")
    protein = Decimal("70")
    for day, demand in enumerate([34, 38, 42, 36, 40], start=1):
        essentials, protein, result = truck_day(day, essentials, protein, demand)
        print_result("food_truck", result)


def simulate_edge_cases() -> None:
    print("\nNo inventory case")
    _, result = fruit_day(1, Decimal("0"), 30)
    print_result("fruit_shop", result)

    print("\nLow inventory case")
    produce, result = fruit_day(1, Decimal("42"), 30)
    print_result("fruit_shop", result)
    _, result = fruit_day(2, produce, 30)
    print_result("fruit_shop", result)


def main() -> None:
    simulate_fruit_shop()
    simulate_food_truck()
    simulate_edge_cases()


if __name__ == "__main__":
    main()
