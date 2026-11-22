"""Shared vocabulary for deterministic food matching and edible weight validation."""

from decimal import Decimal

MASS_FACTORS = {
    "g": Decimal("1"), "gram": Decimal("1"), "grams": Decimal("1"), "克": Decimal("1"), "公克": Decimal("1"),
    "kg": Decimal("1000"), "kilogram": Decimal("1000"), "kilograms": Decimal("1000"),
    "千克": Decimal("1000"), "公斤": Decimal("1000"),
    "mg": Decimal("0.001"), "milligram": Decimal("0.001"), "milligrams": Decimal("0.001"), "毫克": Decimal("0.001"),
}
HOUSEHOLD_UNITS = frozenset({
    "碗", "杯", "个", "枚", "根", "块", "片", "份", "勺", "小把", "把", "汤匙", "茶匙", "ml", "毫升",
    "bowl", "bowls", "cup", "cups", "piece", "pieces", "serving", "servings", "handful", "handfuls",
    "tbsp", "tsp", "tablespoon", "teaspoon",
})

# Exact qualifiers only. Generic preparation words can't identify a raw/cooked variant
# unless the food name already provides the relevant food identity.
PREPARATIONS = {
    "raw": "raw", "生": "raw", "生的": "raw", "未烹调": "raw", "uncooked": "raw",
    "dry": "dry", "干": "dry",
    "cooked": "cooked", "熟": "cooked", "熟的": "cooked",
    "as sold": "as_sold",
    "roasted": "roasted", "roast": "roasted", "烤": "roasted",
    "stewed": "stewed", "炖": "stewed",
    "boiled": "boiled", "煮": "boiled", "水煮": "boiled",
    "hard-boiled": "hard-boiled", "全熟水煮": "hard-boiled",
    "poached": "poached", "水煮荷包": "poached",
    "baked": "baked", "烘烤": "baked",
}
STATES = frozenset({"raw", "dry", "cooked", "as_sold"})
PORTION_UNITS = {
    "usda large egg": {"whole_egg_raw": 88374, "whole_egg_hard_boiled": 92500},
    "美标大号鸡蛋": {"whole_egg_raw": 88374, "whole_egg_hard_boiled": 92500},
    "usda medium banana": {"banana_raw": 93515},
    "美标中等香蕉": {"banana_raw": 93515},
}
