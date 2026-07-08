import asyncio
import re

import httpx

SEARCH_URL = "https://www.mcdonalds.com.cn/ajaxs/search_by_point"
HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer": "https://www.mcdonalds.com.cn/store",
    "Origin": "https://www.mcdonalds.com.cn",
}


async def probe_endpoints() -> None:
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        response = await client.get("https://www.mcdonalds.com.cn/store", headers=HEADERS)
        text = response.text
        endpoints = sorted(set(re.findall(r"/ajaxs/[a-zA-Z0-9_]+", text)))
        print("endpoints in html:", endpoints)
        for name in ("search_by_keyword", "search_by_city", "search_by_bounds", "get_store_list"):
            url = f"https://www.mcdonalds.com.cn/ajaxs/{name}"
            for payload in (
                {"keyword": "上海"},
                {"city": "上海市"},
                {"point": "31.2,121.5"},
            ):
                try:
                    result = await client.post(url, data=payload, headers=HEADERS)
                    print(name, payload, result.status_code, result.text[:100])
                except Exception as exc:
                    print(name, payload, "ERR", exc)


async def probe_grid_density() -> None:
    async with httpx.AsyncClient(timeout=30) as client:
        points = [
            (39.9, 116.4),
            (39.92, 116.4),
            (39.9, 116.42),
            (22.5, 114.0),
            (30.5, 114.3),
        ]
        for lat, lng in points:
            response = await client.post(
                SEARCH_URL,
                data={"point": f"{lat},{lng}"},
                headers=HEADERS,
            )
            payload = response.json()
            data = payload.get("data") or []
            max_dist = max((row.get("_distance") or 0) for row in data) if data else 0
            print(f"({lat},{lng}) count={payload.get('count')} returned={len(data)} max_dist={max_dist}")


if __name__ == "__main__":
    asyncio.run(probe_endpoints())
    asyncio.run(probe_grid_density())
