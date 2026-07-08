"""Probe KFC superapp / CRM / wayback endpoints."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx

OUT = Path(__file__).resolve().parent / "kfc_probe_out"
OUT.mkdir(exist_ok=True)

BROWSER = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
MOBILE = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148"
)

CANDIDATES = [
    ("POST", "http://www.kfc.com.cn/kfccda/ashx/GetStoreList.ashx?op=cname", {"data": {"cname": "北京", "pid": "", "pageIndex": "1", "pageSize": "10"}}),
    ("POST", "http://www.kfc.com.cn/kfccda/ashx/GetStoreList.ashx?op=keyword", {"data": {"cname": "", "pid": "", "keyword": "北京", "pageIndex": "1", "pageSize": "10"}}),
    ("GET", "https://order.kfc.com.cn/preorder-portal/api/v2/store/list", {}),
    ("POST", "https://order.kfc.com.cn/preorder-portal/api/v2/store/list", {"json": {"cityId": 1, "pageIndex": 1, "pageSize": 50}}),
    ("POST", "https://order.kfc.com.cn/preorder-portal/api/v2/store/nearby", {"json": {"latitude": 39.9, "longitude": 116.4, "pageSize": 50}}),
    ("GET", "https://appcommon.kfc.com.cn/superapp/api/v2/store/list", {}),
    ("POST", "https://appcommon.kfc.com.cn/superapp/api/v2/store/list", {"json": {"cityId": 1}}),
    ("GET", "https://appcommon.kfc.com.cn/superapp/api/v2/city/list", {}),
    ("POST", "https://appcommon.kfc.com.cn/superapp/api/v2/city/list", {"json": {}}),
    ("GET", "https://dynamicad.kfc.com.cn/api/store/nearby", {}),
    ("POST", "https://dynamicad.kfc.com.cn/api/store/nearby", {"json": {"lat": 39.9, "lng": 116.4}}),
    ("GET", "https://rnorder.kfc.com.cn/store/list", {}),
    ("POST", "https://rnorder.kfc.com.cn/store/list", {"json": {"cityId": 1}}),
    ("GET", "https://login.kfc.com.cn/api/store/list", {}),
    # wayback snapshot of legacy API
    ("POST", "https://web.archive.org/web/2023/https://www.kfc.com.cn/kfccda/ashx/GetStoreList.ashx?op=cname", {"data": {"cname": "北京", "pid": "", "pageIndex": "1", "pageSize": "10"}}),
]


async def main() -> None:
    async with httpx.AsyncClient(timeout=40, follow_redirects=True) as client:
        for i, (method, url, kwargs) in enumerate(CANDIDATES):
            headers = {
                "User-Agent": MOBILE if "superapp" in url or "order.kfc" in url else BROWSER,
                "Accept": "application/json, text/plain, */*",
                "Referer": "https://order.kfc.com.cn/",
            }
            try:
                r = await client.request(method, url, headers=headers, **kwargs)
                path = OUT / f"candidate_{i}.bin"
                path.write_bytes(r.content)
                text = r.text[:300]
                ok_json = r.text.strip().startswith("{") or r.text.strip().startswith("[")
                print(i, method, r.status_code, url[:80], "json" if ok_json else "html", len(r.content))
                if ok_json:
                    try:
                        data = r.json()
                        if isinstance(data, dict):
                            print("   keys", list(data.keys())[:10])
                            for k in ("Table1", "data", "stores", "storeList", "body"):
                                if k in data and isinstance(data[k], list):
                                    print(f"   {k} len={len(data[k])}")
                    except json.JSONDecodeError:
                        pass
            except Exception as exc:
                print(i, "ERR", url[:80], exc)


if __name__ == "__main__":
    asyncio.run(main())
