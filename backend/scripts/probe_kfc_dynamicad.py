"""Probe dynamicad KFC store API with wrapped body."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import httpx

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
OUT = Path(__file__).resolve().parent / "kfc_probe_out"


def wrap(params: dict) -> dict:
    return {**params, "encodeList": [], "isFromCustomerClient": True, "secretKey": "kfc"}


def main() -> None:
    OUT.mkdir(exist_ok=True)
    headers = {
        "User-Agent": UA,
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Referer": "https://order.kfc.com.cn/",
    }
    bases = [
        "https://dynamicad.kfc.com.cn",
        "https://orders.kfc.com.cn/preorder-portal",
        "https://wxapp.kfc.com.cn",
    ]
    paths = [
        "/api/v2/city/cities",
        "/api/v2/store/searchByCityCodeAndKeyword",
        "/api/v2/store/searchByLbs",
    ]
    body = wrap(
        {
            "versionNum": "5",
            "brand": "KFC",
            "business": "preorder",
            "portalType": "WAP",
            "deviceId": str(uuid.uuid4()),
            "gbCityCode": "110100",
            "keyword": "",
            "pageIndex": 1,
            "pageSize": 20,
            "mylat": "39.9042",
            "mylng": "116.4074",
        }
    )
    with httpx.Client(timeout=30, headers=headers, follow_redirects=True) as c:
        for base in bases:
            for path in paths:
                url = base + path
                for method in ("GET", "POST"):
                    try:
                        r = c.request(
                            method,
                            url,
                            content=json.dumps(body).encode() if method == "POST" else None,
                        )
                        ok = r.text.strip().startswith("{") and "120000002" not in r.text
                        print(method, url, r.status_code, len(r.content), "OK" if ok else r.text[:80])
                        if ok and len(r.content) > 100:
                            OUT.joinpath("dynamicad_hit.json").write_text(r.text, encoding="utf-8")
                            return
                    except Exception as exc:
                        print("ERR", url, exc)


if __name__ == "__main__":
    main()
