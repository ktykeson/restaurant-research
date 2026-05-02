"""Classify a Place as no-website / social-only / has-site."""
from __future__ import annotations

import re
from typing import Optional

SOCIAL_REGEX = re.compile(
    r"(facebook\.com|fb\.me|fb\.com|instagram\.com|instagr\.am|"
    r"linktr\.ee|linktree\.com|beacons\.ai|carrd\.co|"
    r"tiktok\.com|twitter\.com|x\.com|threads\.net|"
    r"wa\.me|whatsapp\.com|t\.me|telegram\.me|"
    r"linkedin\.com|youtube\.com|youtu\.be|pinterest\.com|"
    r"bit\.ly|goo\.gl|tinyurl\.com|t\.co|m\.me|snapchat\.com)",
    re.IGNORECASE,
)


def classify(place: dict, min_reviews: int = 0) -> Optional[str]:
    """Return 'no_website', 'social_only', 'has_site', or None to skip.

    `min_reviews`: drop places with fewer than this many user ratings (0 = off).
    Used as a cheap proxy for "still a real, active business" so the caller
    doesn't waste time on ghost listings.
    """
    status = place.get("businessStatus")
    if status and status != "OPERATIONAL":
        return None  # closed / temporarily closed
    if min_reviews and (place.get("userRatingCount") or 0) < min_reviews:
        return None
    uri = (place.get("websiteUri") or "").strip()
    if not uri:
        return "no_website"
    if SOCIAL_REGEX.search(uri):
        return "social_only"
    return "has_site"
