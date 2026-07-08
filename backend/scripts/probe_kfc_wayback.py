"""Fetch legacy KFC store list from Wayback Machine."""

from __future__ import annotations

import json
from pathlib import Path

import httpx

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
OUT = Path(__file__).resolve().parent / "kfc_probe_out"


def main() -> None:
    OUT.mkdir(exist_ok=True)
    url = (
        "https://web.archive.org/web/2024id_/http://www.kfc.com.cn/"
        "kfccda/ashx/GetStoreList.ashx?op=cname"
    )
    data = {"cname": "\u5317\u4eac", "pid": "", "pageIndex": "1", "pageSize": "10"}
    headers = {"User-Agent": UA, "Referer": "http://www.kfc.com.cn/"}
    with httpx.Client(timeout=60, headers=headers, follow_redirects=True) as c:
        r = c.post(url, data=data)
        OUT.joinpath("wayback_beijing.json").write_bytes(r.content)
        print(r.status_code, len(r.content))
        if r.text.strip().startswith("{"):
            payload = r.json()
            print("keys", payload.keys())
            print("stores", len(payload.get("Table1") or []))


if __name__ == "__main__":
    main()
