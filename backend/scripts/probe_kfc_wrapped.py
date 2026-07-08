"""Test KFC store API with encodeData wrapper (no KBS headers)."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import httpx

BASE = "https://order.kfc.com.cn/preorder-portal"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
OUT = Path(__file__).resolve().parent / "kfc_probe_out"


def wrap_params(params: dict) -> dict:
    return {
        **params,
        "encodeList": [],
        "isFromCustomerClient": True,
        "secretKey": "kfc",
    }


def common_params() -> dict:
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

        # cities - POST with wrapper
        url = BASE + "/api/v2/city/cities"
        body = wrap_params(common_params())
        r = client.post(url, content=json.dumps(body, separators=(",", ":")).encode())
        OUT.joinpath("cities_wrapped.json").write_text(r.text, encoding="utf-8")
        print("cities", r.status_code, len(r.text))

        # stores by city
        url = BASE + "/api/v2/store/searchByCityCodeAndKeyword"
        body = wrap_params(
            {
                **common_params(),
                "gbCityCode": "110100",
                "keyword": "",
                "pageIndex": 1,
                "pageSize": 50,
                "mylatPhone": "",
                "mylngPhone": "",
            }
        )
        r = client.post(url, content=json.dumps(body, separators=(",", ":")).encode())
        OUT.joinpath("stores_wrapped.json").write_text(r.text, encoding="utf-8")
        print("stores", r.status_code, len(r.text))


if __name__ == "__main__":
    main()
