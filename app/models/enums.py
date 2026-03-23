"""Shared enums for core economic schema models."""

from __future__ import annotations

from enum import Enum


class BasketType(str, Enum):
    essentials = "essentials"
    protein = "protein"
    produce = "produce"
    convenience = "convenience"


class TradeSide(str, Enum):
    buy = "buy"
    sell = "sell"


class RegionType(str, Enum):
    suburban = "suburban"
    downtown = "downtown"

