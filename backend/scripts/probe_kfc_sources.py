"""Probe KFC mainland store data sources (no Amap)."""

from __future__ import annotations

import asyncio
import json
import re

import httpx

BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
MOBILE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)

HEADERS = {
    "User-Agent": BROWSER_UA,
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


async def probe_url(client: httpx.AsyncClient, method: str, url: str, **kwargs) -> None:
    try:
        r = await client.request(method, url, **kwargs)
        preview = r.text[:220].replace("\n", " ")
        print(f"{method} {url} -> {r.status_code} {preview}")
        if r.status_code == 200 and r.text.strip().startswith("{"):
            data = r.json()
            if isinstance(data, dict):
                print(f"  keys={list(data.keys())[:12]}")
    except Exception as exc:
        print(f"{method} {url} -> ERR {exc}")


async def scrape_js_urls(html: str, label: str) -> None:
    patterns = [
        r"https?://[^\"'\\s<>]+(?:store|Store|ashx|api|kfc)[^\"'\\s<>]*",
        r"/(?:api|store|kfccda|preorder)[^\"'\\s<>]*",
    ]
    hits: set[str] = set()
    for pat in patterns:
        hits.update(re.findall(pat, html, re.I))
    print(f"--- {label} url hits ({len(hits)}) ---")
    for hit in sorted(hits)[:40]:
        print(" ", hit[:140])


async def main() -> None:
    async with httpx.AsyncClient(
        timeout=30, headers=HEADERS, follow_redirects=True
    ) as browser:
        async with httpx.AsyncClient(
            timeout=30,
            headers={**HEADERS, "User-Agent": MOBILE_UA},
            follow_redirects=True,
        ) as mobile:
            pages = [
                ("browser", browser, "https://www.kfc.com.cn/"),
                ("browser", browser, "https://www.kfc.com.cn/store/"),
                ("browser", browser, "http://www.kfc.com.cn/kfccda/storelist/index.aspx"),
                ("mobile", mobile, "https://m.kfc.com.cn/store/"),
                ("mobile", mobile, "https://m.kfc.com.cn/"),
            ]
            for kind, client, url in pages:
                try:
                    r = await client.get(url)
                    print(f"GET [{kind}] {url} -> {r.status_code} len={len(r.text)}")
                    if r.status_code == 200:
                        scrape_js_urls(r.text, url)
                except Exception as exc:
                    print(f"GET [{kind}] {url} -> ERR {exc}")

            # Legacy ashx on www host (some deployments only expose on HTTPS www)
            data = {"cname": "北京", "pid": "", "pageIndex": "1", "pageSize": "3"}
            for base in (
                "http://www.kfc.com.cn/kfccda/ashx/GetStoreList.ashx?op=cname",
                "https://www.kfc.com.cn/kfccda/ashx/GetStoreList.ashx?op=cname",
                "https://order.kfc.com.cn/kfccda/ashx/GetStoreList.ashx?op=cname",
            ):
                await probe_url(browser, "POST", base, data=data)

            # Preorder portal
            preorder_paths = [
                "https://order.kfc.com.cn/preorder-portal/api/v2/city/list",
                "https://order.kfc.com.cn/preorder-portal/api/v2/store/list",
                "https://order.kfc.com.cn/preorder-portal/api/v2/store/city/list",
                "https://appcommon.kfc.com.cn/api/store/list",
                "https://dynamicad.kfc.com.cn/api/store/list",
            ]
            for url in preorder_paths:
                await probe_url(mobile, "GET", url)
                await probe_url(
                    mobile,
                    "POST",
                    url,
                    json={"cityId": "1", "pageIndex": 1, "pageSize": 10},
                )


if __name__ == "__main__":
    asyncio.run(main())
