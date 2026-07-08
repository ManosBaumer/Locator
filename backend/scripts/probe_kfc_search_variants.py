"""Probe how to list all KFC stores in a city."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import httpx

BASE = "https://order.kfc.com.cn/store-portal"
OUT = Path(__file__).resolve().parent / "kfc_probe_out"
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


def main() -> None:
    OUT.mkdir(exist_ok=True)
    headers = {
        "User-Agent": UA,
        "Content-Type": "application/json",
        "Referer": "https://order.kfc.com.cn/preorder-taro/store",
        "Origin": "https://order.kfc.com.cn",
    }
    lines: list[str] = []
    with httpx.Client(timeout=30, headers=headers) as client:
        for kw in ("", " ", ".", "\u5e97", "\u9910\u5385", "KFC", "1", "a"):
            body = wrap(
                {
                    **common(),
                    "gbCityCode": "110100",
                    "keyword": kw,
                    "pageIndex": 1,
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
            lines.append(f"kw={kw!r} code={j.get('code')} msg={j.get('msg')} stores={len(stores)}")

        for lat, lng in (("39.9042", "116.4074"), ("39.95", "116.40"), ("40.0", "116.5")):
            body = wrap(
                {
                    **common(),
                    "mylat": lat,
                    "mylng": lng,
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
            data = j.get("data") or {}
            stores = data.get("stores") or []
            lines.append(
                f"lbs lat={lat} lng={lng} code={j.get('code')} stores={len(stores)} haveMore={data.get('haveMore')}"
            )
            if stores:
                OUT.joinpath(f"lbs_{lat}_{lng}.json").write_text(r.text, encoding="utf-8")

    OUT.joinpath("search_variants.txt").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
