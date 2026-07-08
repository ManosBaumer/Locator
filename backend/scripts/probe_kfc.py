"""Probe KFC China store list API variants."""

from __future__ import annotations

import asyncio
import json
import re

import httpx

URLS = [
    "http://www.kfc.com.cn/kfccda/ashx/GetStoreList.ashx?op=cname",
    "https://www.kfc.com.cn/kfccda/ashx/GetStoreList.ashx?op=cname",
    "http://www.kfc.com.cn/kfccda/ashx/GetStoreList.ashx?op=province",
    "http://www.kfc.com.cn/kfccda/ashx/GetStoreList.ashx?op=city",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "http://www.kfc.com.cn/kfccda/storelist/index.aspx",
    "Origin": "http://www.kfc.com.cn",
    "X-Requested-With": "XMLHttpRequest",
}


async def try_post(client: httpx.AsyncClient, url: str, data: dict[str, str]) -> None:
    r = await client.post(url, data=data)
    preview = r.text[:200].replace("\n", " ")
    print(f"POST {url}")
    print(f"  data={data} -> {r.status_code} {preview}")
    if r.status_code == 200 and r.text.strip().startswith("{"):
        payload = r.json()
        table1 = payload.get("Table1") or []
        table = payload.get("Table") or []
        print(f"  rowcount={table!r} stores={len(table1)}")
        if table1:
            print(f"  sample keys={list(table1[0].keys())}")


async def main() -> None:
    async with httpx.AsyncClient(timeout=30, headers=HEADERS, follow_redirects=True) as client:
        # Some crawlers visit the store list page first to obtain cookies.
        for page_url in (
            "http://www.kfc.com.cn/kfccda/storelist/index.aspx",
            "https://www.kfc.com.cn/",
        ):
            try:
                r = await client.get(page_url)
                print("warmup", page_url, r.status_code, "cookies", len(client.cookies))
            except Exception as exc:
                print("warmup", page_url, "ERR", exc)

        post_variants = [
            ("http://www.kfc.com.cn/kfccda/ashx/GetStoreList.ashx?op=cname", {}),
            ("http://www.kfc.com.cn/kfccda/ashx/GetStoreList.ashx", {"op": "cname"}),
            ("http://www.kfc.com.cn/kfccda/ashx/GetStoreList.ashx?op=keyword", {}),
            ("http://www.kfc.com.cn/kfccda/ashx/GetStoreList.ashx", {"op": "keyword"}),
        ]
        data = {"cname": "北京", "pid": "", "pageIndex": "1", "pageSize": "3"}
        for url, params in post_variants:
            r = await client.post(url, params=params or None, data=data)
            print("POST", url, "params=", params, "->", r.status_code, r.text[:160].replace("\n", " "))

        home = await client.get("https://www.kfc.com.cn/")
        print("home", home.status_code, len(home.text))
        hits = sorted(set(re.findall(r"[^\"']*(?:GetStoreList|storelist|kfccda|/api/)[^\"']*", home.text, re.I)))
        for hit in hits[:30]:
            print("  hit", hit)


if __name__ == "__main__":
    asyncio.run(main())
