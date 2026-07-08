"""Discover KFC preorder-portal JSON endpoints."""

from __future__ import annotations

import asyncio

import httpx

BASE = "https://order.kfc.com.cn/preorder-portal/api/v2"
PATHS = [
    "/city/list",
    "/cities",
    "/store/list",
    "/store/nearby",
    "/store/city",
    "/store/city/list",
    "/store/all",
    "/store/search",
    "/config",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15",
    "Referer": "https://order.kfc.com.cn/",
    "Accept": "application/json",
}


async def main() -> None:
    async with httpx.AsyncClient(timeout=20, headers=HEADERS, follow_redirects=True) as client:
        for path in PATHS:
            url = BASE + path
            for method in ("GET", "POST"):
                try:
                    r = await client.request(method, url, json={} if method == "POST" else None)
                    if r.status_code == 404:
                        continue
                    print(method, path, r.status_code, r.text[:180].replace("\n", " "))
                except Exception as exc:
                    print(method, path, "ERR", exc)


if __name__ == "__main__":
    asyncio.run(main())
