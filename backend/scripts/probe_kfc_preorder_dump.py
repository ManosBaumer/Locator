"""Probe KFC preorder-portal API and dump JSON responses."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx

MOBILE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)
OUT = Path(__file__).resolve().parent / "kfc_probe_out"
OUT.mkdir(exist_ok=True)


async def dump(client: httpx.AsyncClient, name: str, method: str, url: str, **kwargs) -> None:
    r = await client.request(method, url, **kwargs)
    path = OUT / f"{name}.json"
    path.write_bytes(r.content)
    print(name, method, r.status_code, "bytes", len(r.content), "->", path.name)
    if r.headers.get("content-type", "").startswith("application/json") or r.text.strip().startswith("{"):
        try:
            data = r.json()
            if isinstance(data, dict):
                print("  keys", list(data.keys())[:15])
                for k in ("data", "body", "result", "stores", "cityList", "list"):
                    if k in data:
                        v = data[k]
                        print(f"  {k} type={type(v).__name__}", end="")
                        if isinstance(v, list):
                            print(f" len={len(v)}")
                            if v:
                                print("  sample keys", list(v[0].keys())[:20] if isinstance(v[0], dict) else v[0])
                        else:
                            print()
        except json.JSONDecodeError:
            pass


async def main() -> None:
    headers = {
        "User-Agent": MOBILE_UA,
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://order.kfc.com.cn/",
        "Origin": "https://order.kfc.com.cn",
    }
    async with httpx.AsyncClient(timeout=30, headers=headers, follow_redirects=True) as client:
        base = "https://order.kfc.com.cn/preorder-portal/api/v2"
        await dump(client, "city_list", "GET", f"{base}/city/list")
        await dump(client, "store_list_post", "POST", f"{base}/store/list", json={})
        await dump(client, "store_city_list", "GET", f"{base}/store/city/list")
        # try with city id from city list
        city_data = json.loads((OUT / "city_list.json").read_text(encoding="utf-8"))
        cities = city_data.get("data") or city_data.get("body") or []
        if isinstance(cities, list) and cities:
            sample = cities[0]
            cid = sample.get("cityId") or sample.get("id") or sample.get("gbCityCode")
            print("sample city", sample)
            if cid:
                await dump(
                    client,
                    "store_list_beijing",
                    "POST",
                    f"{base}/store/list",
                    json={"cityId": str(cid), "pageIndex": 1, "pageSize": 50},
                )
                await dump(
                    client,
                    "store_nearby",
                    "POST",
                    f"{base}/store/nearby",
                    json={"cityId": str(cid), "latitude": 39.9, "longitude": 116.4, "pageSize": 50},
                )


if __name__ == "__main__":
    asyncio.run(main())
