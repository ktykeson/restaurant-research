"""Async client for Google Places API (New).

Uses field-mask to fetch websiteUri inline so we never need a second Place
Details call. Built-in retry on 429/5xx with exponential backoff.
"""
from __future__ import annotations

import asyncio
from typing import Optional

import httpx

import config

PLACES_HOST = "https://places.googleapis.com/v1/places"

# Field mask — every field we need lives in one search response. websiteUri
# bumps billing to Place Details Pro tier (~$32/1k); accepted cost.
# Phone + userRatingCount are also Pro-tier — no SKU change. (Adding
# `places.reviews` would jump to Enterprise SKU; intentionally omitted.)
FIELD_MASK = ",".join([
    "places.id",
    "places.displayName",
    "places.googleMapsUri",
    "places.websiteUri",
    "places.location",
    "places.types",
    "places.primaryType",
    "places.businessStatus",
    "places.formattedAddress",
    "places.nationalPhoneNumber",
    "places.internationalPhoneNumber",
    "places.userRatingCount",
    "nextPageToken",
])

DEFAULT_TIMEOUT = httpx.Timeout(20.0, connect=10.0)


class PlacesClient:
    def __init__(
        self,
        api_key: Optional[str] = None,
        max_concurrent: int = 8,
        language_code: str = "en",
        region_code: str = "",
    ):
        self.api_key = api_key or config.get_api_key()
        if not self.api_key:
            raise RuntimeError(
                "Google Places API key is not set. Open Settings in the app and paste your key."
            )
        self.language_code = language_code
        self.region_code = region_code
        self._sem = asyncio.Semaphore(max_concurrent)
        self._client = httpx.AsyncClient(timeout=DEFAULT_TIMEOUT)
        self.requests_used = 0

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        await self.aclose()

    def _headers(self) -> dict:
        return {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self.api_key,
            "X-Goog-FieldMask": FIELD_MASK,
        }

    async def _post(self, url: str, body: dict, max_retries: int = 4) -> dict:
        backoff = 1.0
        last_exc: Optional[Exception] = None
        async with self._sem:
            for attempt in range(max_retries):
                try:
                    resp = await self._client.post(url, json=body, headers=self._headers())
                    self.requests_used += 1
                    if resp.status_code == 200:
                        return resp.json()
                    if resp.status_code in (429, 500, 502, 503, 504):
                        await asyncio.sleep(backoff)
                        backoff = min(backoff * 2, 16.0)
                        continue
                    # 4xx other than 429 — non-retryable.
                    raise RuntimeError(
                        f"Places API {resp.status_code}: {resp.text[:300]}"
                    )
                except httpx.RequestError as e:
                    last_exc = e
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, 16.0)
            raise RuntimeError(f"Places API exhausted retries: {last_exc}")

    def _locale(self, language_code: Optional[str], region_code: Optional[str]) -> dict:
        body: dict = {}
        lang = language_code if language_code is not None else self.language_code
        reg = region_code if region_code is not None else self.region_code
        if lang:
            body["languageCode"] = lang
        if reg:
            body["regionCode"] = reg
        return body

    async def search_nearby(
        self,
        lat: float,
        lng: float,
        radius_m: float,
        included_types: list[str],
        max_results: int = 20,
        language_code: Optional[str] = None,
        region_code: Optional[str] = None,
    ) -> list[dict]:
        body = {
            "includedTypes": included_types,
            "maxResultCount": min(max_results, 20),
            "locationRestriction": {
                "circle": {
                    "center": {"latitude": lat, "longitude": lng},
                    "radius": float(radius_m),
                }
            },
            **self._locale(language_code, region_code),
        }
        data = await self._post(f"{PLACES_HOST}:searchNearby", body)
        return data.get("places") or []

    async def search_text(
        self,
        text_query: str,
        lat: float,
        lng: float,
        radius_m: float,
        max_pages: int = 3,
        language_code: Optional[str] = None,
        region_code: Optional[str] = None,
    ) -> list[dict]:
        """Text Search supports pagination up to ~60 results across 3 pages."""
        results: list[dict] = []
        page_token: Optional[str] = None
        for _ in range(max_pages):
            body: dict = {
                "textQuery": text_query,
                "maxResultCount": 20,
                "locationBias": {
                    "circle": {
                        "center": {"latitude": lat, "longitude": lng},
                        "radius": float(radius_m),
                    }
                },
                **self._locale(language_code, region_code),
            }
            if page_token:
                body["pageToken"] = page_token
            data = await self._post(f"{PLACES_HOST}:searchText", body)
            results.extend(data.get("places") or [])
            page_token = data.get("nextPageToken")
            if not page_token:
                break
            # Page tokens require a brief delay to become valid.
            await asyncio.sleep(2.0)
        return results
