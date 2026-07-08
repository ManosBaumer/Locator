import asyncio
import re

import httpx

from app.ingestion.amap_regions import fetch_amap_province_city_tree

KEY = "ac1340d6ebb24662e8f0da0d015fc6e0"
AMAP = "https://restapi.amap.com/v3/place/text"
WALMART = re.compile(r"沃尔玛\s*[\(（]")
SAMS = re.compile(r"山姆会员商店\s*[\(（]")


def ok_walmart(p: dict) -> bool:
    name = p.get("name") or ""
    if not WALMART.search(name):
        return False
    if "有限公司" in name and "店" not in name:
        return False
    if "公交站" in name or "地铁站" in name:
        return False
    type_field = p.get("type") or ""
    return "沃尔玛" in type_field or "超级市场" in type_field


def ok_sams(p: dict) -> bool:
    name = p.get("name") or ""
    if not SAMS.search(name):
        return False
    if "有限公司" in name and "店" not in name:
        return False
    return True


async def fetch_region(client: httpx.AsyncClient, region: str, keyword: str, matcher) -> dict[str, str]:
    stores: dict[str, str] = {}
    page = 1
    while page <= 40:
        response = await client.get(
            AMAP,
            params={
                "key": KEY,
                "keywords": keyword,
                "city": region,
                "offset": 25,
                "page": page,
                "extensions": "base",
            },
        )
        payload = response.json()
        if payload.get("status") != "1":
            break
        pois = payload.get("pois") or []
        if not pois:
            break
        for poi in pois:
            if matcher(poi):
                stores[poi["id"]] = poi["name"]
        if len(pois) < 25:
            break
        page += 1
        await asyncio.sleep(0.02)
    return stores


async def main() -> None:
    async with httpx.AsyncClient(timeout=30) as client:
        tree = await fetch_amap_province_city_tree(client, KEY)
        walmart: dict[str, str] = {}
        sams: dict[str, str] = {}
        for province in tree:
            regions = [province.short_name] if not province.cities else list(province.cities)
            for region in regions:
                walmart.update(await fetch_region(client, region, "沃尔玛(", ok_walmart))
                sams.update(await fetch_region(client, region, "山姆会员商店", ok_sams))
                await asyncio.sleep(0.02)
        print("walmart", len(walmart))
        print("sams", len(sams))
        print("total", len(walmart) + len(sams))


if __name__ == "__main__":
    asyncio.run(main())
