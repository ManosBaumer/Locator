"""Grid LBS crawl to count Beijing KFC stores."""

from __future__ import annotations

import json
import math
import uuid

import httpx

BASE = "https://order.kfc.com.cn/store-portal"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def wrap(p: dict) -> dict:
    return {**p, "encodeList": [], "isFromCustomerClient": True, "secretKey": "kfc"}


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


def grid_points(center_lat: float, center_lng: float, span_km: float, step_km: float):
    lat_step = step_km / 111.0
    lng_step = step_km / (111.0 * max(math.cos(math.radians(center_lat)), 0.2))
    steps = int(span_km / step_km)
    for i in range(-steps, steps + 1):
        for j in range(-steps, steps + 1):
            yield center_lat + i * lat_step, center_lng + j * lng_step


def main() -> None:
    headers = {
        "User-Agent": UA,
        "Content-Type": "application/json",
        "Referer": "https://order.kfc.com.cn/preorder-taro/store",
        "Origin": "https://order.kfc.com.cn",
    }
    seen: set[str] = set()
    with httpx.Client(timeout=30, headers=headers) as client:
        # keyword space pagination
        for page in range(1, 6):
            body = wrap(
                {
                    **common(),
                    "gbCityCode": "110100",
                    "keyword": " ",
                    "pageIndex": page,
                    "pageSize": 50,
                    "mylatPhone": "",
                    "mylngPhone": "",
                }
            )
            r = client.post(
                BASE + "/api/v2/store/searchByCityCodeAndKeyword",
                content=json.dumps(body, separators=(",", ":")).encode(),
            )
            j = r.json()
            stores = (j.get("data") or {}).get("stores") or []
            for s in stores:
                if s.get("typeCode") == "H" and s.get("storecode"):
                    seen.add(s["storecode"])
            print("page", page, "batch", len(stores), "total", len(seen), "haveMore", (j.get("data") or {}).get("haveMore"))

        # LBS grid around Beijing
        lbs_seen: set[str] = set()
        for lat, lng in grid_points(39.9042, 116.4074, span_km=25, step_km=5):
            body = wrap(
                {
                    **common(),
                    "mylat": f"{lat:.6f}",
                    "mylng": f"{lng:.6f}",
                    "gbCityCode": "110100",
                    "pageIndex": 1,
                    "pageSize": 50,
                }
            )
            r = client.post(
                BASE + "/api/v2/store/searchByLbs",
                content=json.dumps(body, separators=(",", ":")).encode(),
            )
            j = r.json()
            if j.get("code") != 0:
                continue
            for s in (j.get("data") or {}).get("stores") or []:
                if s.get("typeCode") == "H" and s.get("storecode"):
                    lbs_seen.add(s["storecode"])
        print("lbs grid unique H stores", len(lbs_seen))


if __name__ == "__main__":
    main()
