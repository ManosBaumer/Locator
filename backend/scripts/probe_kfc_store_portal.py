"""Test KFC store-portal API (correct base domain)."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import httpx

BASE = "https://order.kfc.com.cn/store-portal"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
OUT = Path(__file__).resolve().parent / "kfc_probe_out"


def wrap(params: dict) -> dict:
    return {**params, "encodeList": [], "isFromCustomerClient": True, "secretKey": "kfc"}


def common() -> dict:
    return {
        "versionNum": "5",
        "brand": "KFC",
        "business": "preorder",
        "portalType": "WAP",
        "deviceId": str(uuid.uuid4()),
    }


def main() -> None:
    OUT.mkdir(exist_ok=True)
    headers = {
        "User-Agent": UA,
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "Referer": "https://order.kfc.com.cn/preorder-taro/store",
        "Origin": "https://order.kfc.com.cn",
    }
    with httpx.Client(timeout=30, headers=headers, follow_redirects=True) as client:
        client.get("https://order.kfc.com.cn/preorder-taro/store")

        url = BASE + "/api/v2/city/cities"
        r = client.post(url, content=json.dumps(wrap(common()), separators=(",", ":")).encode())
        OUT.joinpath("cities_store_portal.json").write_text(r.text, encoding="utf-8")
        print("cities", r.status_code, len(r.text))

        url = BASE + "/api/v2/store/searchByCityCodeAndKeyword"
        body = wrap(
            {
                **common(),
                "gbCityCode": "110100",
                "keyword": "",
                "pageIndex": 1,
                "pageSize": 50,
                "mylatPhone": "",
                "mylngPhone": "",
            }
        )
        r = client.post(url, content=json.dumps(body, separators=(",", ":")).encode())
        OUT.joinpath("stores_beijing_store_portal.json").write_text(r.text, encoding="utf-8")
        print("stores", r.status_code, len(r.text))


if __name__ == "__main__":
    main()
