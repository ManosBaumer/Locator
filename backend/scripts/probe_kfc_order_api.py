"""Probe KFC preorder-portal store API request shapes."""

from __future__ import annotations

import asyncio
import json

import httpx

URL = "https://order.kfc.com.cn/preorder-portal/api/v2/store/list"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148"
    ),
    "Referer": "https://order.kfc.com.cn/",
    "Content-Type": "application/json",
    "Accept": "application/json",
}


async def try_call(client: httpx.AsyncClient, label: str, *, method: str = "GET", **kwargs) -> None:
    r = await client.request(method, URL, **kwargs)
    preview = r.text[:240].replace("\n", " ")
    print(label, r.status_code, preview)


async def main() -> None:
    async with httpx.AsyncClient(timeout=20, headers=HEADERS, follow_redirects=True) as client:
        await try_call(client, "GET bare")
        bodies = [
            {},
            {"cityId": 1},
            {"cityId": "1"},
            {"cityCode": "010"},
            {"lat": 39.9, "lng": 116.4},
            {"latitude": 39.9, "longitude": 116.4},
            {"brand": "KFC", "cityId": 1},
        ]
        for i, body in enumerate(bodies):
            await try_call(client, f"POST body{i}", method="POST", json=body)
        params = [
            {"cityId": 1},
            {"lat": 39.9, "lng": 116.4},
        ]
        for i, param in enumerate(params):
            await try_call(client, f"GET params{i}", params=param)


if __name__ == "__main__":
    asyncio.run(main())
