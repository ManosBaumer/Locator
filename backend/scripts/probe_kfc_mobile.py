"""Probe order.kfc.com.cn and mobile API hosts for store endpoints."""

from __future__ import annotations

import asyncio
import re

import httpx

HOSTS = [
    "https://order.kfc.com.cn",
    "https://rnorder.kfc.com.cn",
    "https://orders.kfc.com.cn",
    "https://appcommon.kfc.com.cn",
    "https://mobile-api.kfc.com.cn",
    "https://dynamicad.kfc.com.cn",
    "https://login.kfc.com.cn",
]

PATHS = [
    "/store/list",
    "/store/v2/list",
    "/preorder-portal/api/v2/store/list",
    "/preorder-portal/store/list",
    "/api/store/list",
    "/api/v2/store/list",
    "/CRM/superapp_wechat/lbs/stores",
    "/CRM/superapp_wechat/store/nearby",
    "/preorder/store/list",
]


async def main() -> None:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148"
        ),
        "Referer": "https://www.kfc.com.cn/",
    }
    async with httpx.AsyncClient(timeout=20, headers=headers, follow_redirects=True) as client:
        for host in HOSTS:
            try:
                r = await client.get(host + "/")
                print("ROOT", host, r.status_code, len(r.text))
                for m in re.findall(r"https?://[^\"'\\s<>]+", r.text):
                    if "store" in m.lower() or "api" in m.lower():
                        print("  url", m[:140])
            except Exception as exc:
                print("ROOT", host, "ERR", exc)
            for path in PATHS:
                url = host + path
                try:
                    r = await client.get(url)
                    if r.status_code not in (404, 403):
                        preview = r.text[:120].replace("\n", " ")
                        print("GET", url, r.status_code, preview)
                except Exception:
                    pass


if __name__ == "__main__":
    asyncio.run(main())
