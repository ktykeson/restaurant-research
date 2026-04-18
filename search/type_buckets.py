"""Narrow includedTypes buckets for searchNearby.

Splitting types into buckets keeps individual searches under the API's 20-result cap,
maximising recall in dense areas. Localized text-search queries now live in
query_profiles.py so they can be toggled per region.
"""
from __future__ import annotations

# Each bucket is a (label, includedTypes) pair. Restricted to <=50 types per call.
NEARBY_BUCKETS: list[tuple[str, list[str]]] = [
    ("restaurant_core", [
        "restaurant",
    ]),
    ("ethnic_restaurants", [
        "italian_restaurant",
        "chinese_restaurant",
        "french_restaurant",
        "japanese_restaurant",
        "indian_restaurant",
        "thai_restaurant",
        "korean_restaurant",
        "mexican_restaurant",
        "american_restaurant",
        "mediterranean_restaurant",
        "vietnamese_restaurant",
        "turkish_restaurant",
        "greek_restaurant",
        "lebanese_restaurant",
        "spanish_restaurant",
        "brazilian_restaurant",
        "indonesian_restaurant",
        "middle_eastern_restaurant",
        "afghani_restaurant",
        "ramen_restaurant",
        "sushi_restaurant",
        "seafood_restaurant",
        "steak_house",
        "vegan_restaurant",
        "vegetarian_restaurant",
        "fine_dining_restaurant",
    ]),
    ("cafe_bakery", [
        "cafe",
        "bakery",
        "coffee_shop",
        "tea_house",
        "dessert_shop",
        "donut_shop",
        "bagel_shop",
    ]),
    ("bar_pub", [
        "bar",
        "pub",
        "wine_bar",
        "night_club",
    ]),
    ("takeaway_delivery", [
        "meal_takeaway",
        "meal_delivery",
    ]),
    ("fast_casual", [
        "pizza_restaurant",
        "fast_food_restaurant",
        "sandwich_shop",
        "hamburger_restaurant",
        "ice_cream_shop",
        "barbecue_restaurant",
        "buffet_restaurant",
        "breakfast_restaurant",
        "brunch_restaurant",
        "diner",
        "cafeteria",
        "bar_and_grill",
    ]),
]

