import asyncio

import httpx

SEARCH_URL = "https://www.mcdonalds.com.cn/ajaxs/search_by_point"
HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer": "https://www.mcdonalds.com.cn/store",
    "Origin": "https://www.mcdonalds.com.cn",
}


def grid_points(min_lat: float, max_lat: float, min_lng: float, max_lng: float, step: float):
    lat = min_lat
    while lat <= max_lat:
        lng = min_lng
        while lng <= max_lng:
            yield round(lat, 4), round(lng, 4)
            lng += step
        lat += step


async def collect_bbox(min_lat, max_lat, min_lng, max_lng, step: float) -> dict[str, dict]:
    stores: dict[str, dict] = {}
    points = list(grid_points(min_lat, max_lat, min_lng, max_lng, step))
    async with httpx.AsyncClient(timeout=30) as client:
        for index, (lat, lng) in enumerate(points):
            response = await client.post(
                SEARCH_URL,
                data={"point": f"{lat},{lng}"},
                headers=HEADERS,
            )
            response.raise_for_status()
            for row in response.json().get("data") or []:
                stores[row["id"]] = row
            if index % 50 == 0:
                await asyncio.sleep(0.05)
    return stores


async def main() -> None:
    # Guangdong approximate bbox
    stores = await collect_bbox(20.5, 25.5, 109.5, 117.5, 0.08)
    print("guangdong step=0.08 points", len(list(grid_points(20.5, 25.5, 109.5, 117.5, 0.08))))
    print("unique stores", len(stores))


if __name__ == "__main__":
    asyncio.run(main())
