"""Estimate KFC store count via store-portal API."""

from __future__ import annotations

import asyncio
import json
import uuid

import httpx

BASE = "https://order.kfc.com.cn/store-portal"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
KEYWORD = "\u80af\u5fb7\u57fa"


def wrap(params: dict) -> dict:
    return {**params, "encodeList": [], "isFromCustomerClient": True, "secretKey": "kfc"}


def common() -> dict:
    return {
        "portalType": "WAP",
        "portalSource": "",
        "channelName": "Mobile Web",
        "channelId": "13",
        "brand": "KFC_PRE",
        "business": "preorder",
        "sessionId": str(uuid.uuid4()),
        "deviceId": str(uuid.uuid4()),
        "clientVersion": "v6.626(86ae5fef)",
        "env": "prod",
    }


async def fetch_city_stores(
    client: httpx.AsyncClient, gb_city_code: str, page_size: int = 50
) -> tuple[int, bool]:
    seen: set[str] = set()
    page = 1
    have_more = True
    while have_more and page <= 20:
        body = wrap(
            {
                **common(),
                "gbCityCode": gb_city_code,
                "keyword": KEYWORD,
                "pageIndex": page,
                "pageSize": page_size,
                "mylatPhone": "",
                "mylngPhone": "",
            }
        )
        r = await client.post(
            BASE + "/api/v2/store/searchByCityCodeAndKeyword",
            content=json.dumps(body, separators=(",", ":")).encode(),
        )
        payload = r.json()
        if payload.get("code") != 0:
            break
        data = payload.get("data") or {}
        stores = data.get("stores") or []
        for store in stores:
            code = store.get("storecode")
            if code and store.get("typeCode") == "H":
                seen.add(code)
        have_more = bool(data.get("haveMore"))
        page += 1
        await asyncio.sleep(0.05)
    return len(seen), have_more


async def main() -> None:
    headers = {
        "User-Agent": UA,
        "Content-Type": "application/json",
        "Referer": "https://order.kfc.com.cn/preorder-taro/store",
        "Origin": "https://order.kfc.com.cn",
    }
    async with httpx.AsyncClient(timeout=30, headers=headers) as client:
        r = await client.post(
            BASE + "/api/v2/city/cities",
            content=json.dumps(wrap(common()), separators=(",", ":")).encode(),
        )
        cities_payload = r.json()
        all_cities = (cities_payload.get("data") or {}).get("allCities") or []
        print("cities", len(all_cities))

        sample_codes = ["110100", "310100", "440100", "440300", "330100"]
        total = 0
        for code in sample_codes:
            count, more = await fetch_city_stores(client, code)
            print(code, count, "have_more_after", more)
            total += count
        print("sample total", total)


if __name__ == "__main__":
    asyncio.run(main())
