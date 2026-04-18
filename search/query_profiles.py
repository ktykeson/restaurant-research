"""Localized text-search profiles.

Each profile is a toggleable checkbox in the UI that expands into a set of
language- or cuisine-specific text queries. Region + cuisine profiles stack:
e.g. a region in Zürich might default to ["de_swiss"] while the user can
also tick ["italian"] and ["turkish"] to catch Italian/Turkish spots that
are mis-categorised by Google.
"""
from __future__ import annotations

from typing import Optional

# id: stable identifier stored in the DB / selection state.
# label: UI-facing name.
# queries: raw text queries sent to Places `searchText`.
# suggested_language_code: when this profile is the region's default, the
#     crawler sends this as `languageCode` to improve match quality.
PROFILES: list[dict] = [
    {"id": "en", "label": "English / generic", "group": "Western European", "suggested_language_code": "en",
     "queries": ["Restaurant", "Cafe", "Bar", "Pub", "Bakery", "Bistro",
                 "Pizzeria", "Takeaway", "Diner", "Food court"]},
    {"id": "de_swiss", "label": "Swiss-German", "group": "Western European", "suggested_language_code": "de",
     "queries": ["Restaurant", "Beizli", "Wirtschaft", "Gasthof", "Gasthaus",
                 "Imbiss", "Take Away", "Pizzeria", "Trattoria", "Konditorei",
                 "Café", "Bistro", "Kebab", "Döner"]},
    {"id": "de", "label": "German", "group": "Western European", "suggested_language_code": "de",
     "queries": ["Restaurant", "Gasthaus", "Gasthof", "Wirtshaus", "Imbiss",
                 "Schnellimbiss", "Café", "Bistro", "Pizzeria", "Konditorei",
                 "Biergarten", "Bäckerei", "Eisdiele"]},
    {"id": "it", "label": "Italian", "group": "Western European", "suggested_language_code": "it",
     "queries": ["Ristorante", "Trattoria", "Osteria", "Pizzeria", "Bar",
                 "Caffè", "Pasticceria", "Gelateria", "Enoteca",
                 "Tavola Calda", "Paninoteca", "Rosticceria"]},
    {"id": "fr", "label": "French", "group": "Western European", "suggested_language_code": "fr",
     "queries": ["Restaurant", "Brasserie", "Bistrot", "Café", "Boulangerie",
                 "Pâtisserie", "Crêperie", "Pizzeria", "Salon de thé",
                 "Tabac", "Traiteur"]},
    {"id": "es", "label": "Spanish", "group": "Western European", "suggested_language_code": "es",
     "queries": ["Restaurante", "Bar", "Cafetería", "Panadería", "Pastelería",
                 "Heladería", "Taberna", "Tasca", "Pizzería", "Bocadillería",
                 "Asador", "Marisquería"]},
    {"id": "pt", "label": "Portuguese", "group": "Western European", "suggested_language_code": "pt",
     "queries": ["Restaurante", "Café", "Bar", "Padaria", "Confeitaria",
                 "Pizzaria", "Pastelaria", "Churrascaria", "Lanchonete"]},
    {"id": "nl", "label": "Dutch", "group": "Western European", "suggested_language_code": "nl",
     "queries": ["Restaurant", "Café", "Eetcafé", "Bakkerij",
                 "Bar", "Pizzeria", "Broodjeszaak", "Lunchroom"]},
    {"id": "pl", "label": "Polish", "group": "Eastern European", "suggested_language_code": "pl",
     "queries": ["Restauracja", "Bar", "Kawiarnia", "Piekarnia",
                 "Cukiernia", "Pizzeria", "Karczma", "Pierogarnia"]},
    {"id": "ru", "label": "Russian", "group": "Eastern European", "suggested_language_code": "ru",
     "queries": ["Ресторан", "Кафе", "Столовая", "Бар",
                 "Пекарня", "Пиццерия", "Кондитерская", "Кофейня"]},
    {"id": "tr", "label": "Turkish", "group": "Middle Eastern", "suggested_language_code": "tr",
     "queries": ["Restoran", "Lokanta", "Kebapçı", "Pideci", "Dönerci",
                 "Köfteci", "Kahvehane", "Pastane", "Börekçi", "Kafe",
                 "Çay Bahçesi", "Meyhane"]},
    {"id": "ar", "label": "Arabic", "group": "Middle Eastern", "suggested_language_code": "ar",
     "queries": ["مطعم", "مقهى", "مخبز", "كافتيريا",
                 "شاورما", "فلافل", "كبدة", "فول"]},
    {"id": "ja", "label": "Japanese", "group": "East Asian", "suggested_language_code": "ja",
     "queries": ["レストラン", "カフェ", "居酒屋", "焼肉", "寿司",
                 "ラーメン", "そば", "うどん", "定食", "喫茶店",
                 "食堂", "バー"]},
    {"id": "zh", "label": "Chinese", "group": "East Asian", "suggested_language_code": "zh",
     "queries": ["餐厅", "饭店", "咖啡厅", "面馆", "火锅店",
                 "烧烤", "小吃", "茶餐厅", "酒吧", "面包店"]},
    {"id": "ko", "label": "Korean", "group": "East Asian", "suggested_language_code": "ko",
     "queries": ["식당", "레스토랑", "카페", "고깃집", "분식",
                 "치킨", "제과점", "술집", "포장마차", "횟집"]},
    {"id": "th", "label": "Thai", "group": "South / Southeast Asian", "suggested_language_code": "th",
     "queries": ["ร้านอาหาร", "คาเฟ่", "ร้านกาแฟ", "ร้านเบเกอรี่",
                 "ผับ", "บาร์", "ร้านก๋วยเตี๋ยว", "ร้านส้มตำ"]},
    {"id": "vi", "label": "Vietnamese", "group": "South / Southeast Asian", "suggested_language_code": "vi",
     "queries": ["Nhà hàng", "Quán ăn", "Quán cà phê", "Quán nhậu",
                 "Quán phở", "Bánh mì", "Bún bò", "Cơm tấm"]},
    {"id": "hi", "label": "Hindi / Indian", "group": "South / Southeast Asian", "suggested_language_code": "hi",
     "queries": ["रेस्तरां", "कैफे", "ढाबा", "भोजनालय",
                 "मिठाई की दुकान", "Restaurant", "Dhaba", "Sweets"]},
]

PROFILE_BY_ID = {p["id"]: p for p in PROFILES}

# ISO-2 country code -> suggested profile id. Used when a new region is
# geocoded so sensible defaults get pre-ticked.
COUNTRY_DEFAULTS: dict[str, list[str]] = {
    "CH": ["de_swiss"],
    "DE": ["de"], "AT": ["de"],
    "IT": ["it"], "SM": ["it"], "VA": ["it"],
    "FR": ["fr"], "MC": ["fr"], "LU": ["fr", "de"],
    "BE": ["fr", "nl"],
    "ES": ["es"], "MX": ["es"], "AR": ["es"], "CL": ["es"], "CO": ["es"], "PE": ["es"],
    "PT": ["pt"], "BR": ["pt"],
    "TR": ["tr"],
    "JP": ["ja"],
    "CN": ["zh"], "TW": ["zh"], "HK": ["zh"], "MO": ["zh"], "SG": ["zh", "en"],
    "KR": ["ko"],
    "SA": ["ar"], "AE": ["ar"], "EG": ["ar"], "QA": ["ar"], "KW": ["ar"],
    "BH": ["ar"], "OM": ["ar"], "JO": ["ar"], "MA": ["ar", "fr"],
    "TN": ["ar", "fr"], "DZ": ["ar", "fr"], "LB": ["ar", "fr"],
    "TH": ["th"],
    "VN": ["vi"],
    "IN": ["hi", "en"],
    "RU": ["ru"], "BY": ["ru"], "KZ": ["ru"],
    "PL": ["pl"],
    "NL": ["nl"],
    "US": ["en"], "GB": ["en"], "CA": ["en", "fr"], "AU": ["en"], "NZ": ["en"],
    "IE": ["en"], "ZA": ["en"],
}


def profiles_for_country(country_code: Optional[str]) -> list[str]:
    if not country_code:
        return ["en"]
    return COUNTRY_DEFAULTS.get(country_code.upper(), ["en"])


def queries_for_profiles(profile_ids: list[str]) -> list[str]:
    """Union of queries across the given profiles, de-duplicated, order-preserving."""
    seen: set[str] = set()
    out: list[str] = []
    for pid in profile_ids:
        p = PROFILE_BY_ID.get(pid)
        if not p:
            continue
        for q in p["queries"]:
            if q not in seen:
                seen.add(q)
                out.append(q)
    return out


def primary_language(profile_ids: list[str]) -> Optional[str]:
    for pid in profile_ids:
        p = PROFILE_BY_ID.get(pid)
        if p and p.get("suggested_language_code"):
            return p["suggested_language_code"]
    return None
