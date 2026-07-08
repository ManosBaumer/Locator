"""Probe legacy KFC GetStoreList with browser User-Agent."""

from __future__ import annotations

import json
from pathlib import Path

import httpx

URL = "http://www.kfc.com.cn/kfccda/ashx/GetStoreList.ashx?op=cname"
PAGE = "http://www.kfc.com.cn/kfccda/storelist/index.aspx"

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
MOBILE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)

OUT = Path(__file__).resolve().parent / "kfc_probe_out"
OUT.mkdir(exist_ok=True)


def try_fetch(client: httpx.Client, label: str, ua: str) -> None:
    client.headers["User-Agent"] = ua
    for warm in (PAGE, "http://www.kfc.com.cn/", "https://m.kfc.com.cn/store/"):
        try:
            r = client.get(warm)
            print(label, "warmup", warm, r.status_code, len(client.cookies))
        except Exception as exc:
            print(label, "warmup err", warm, exc)

    for data in (
        {"cname": "北京", "pid": "", "pageIndex": "1", "pageSize": "5"},
        {"cname": "北京", "pid": "", "pageIndex": 1, "pageSize": 5},
    ):
        r = client.post(
            URL,
            data=data,
            headers={
                "Referer": PAGE,
                "Origin": "http://www.kfc.com.cn",
                "X-Requested-With": "XMLHttpRequest",
                "Accept": "application/json, text/javascript, */*; q=0.01",
            },
        )
        print(label, "POST", r.status_code, r.headers.get("content-type"), r.text[:120])
        if r.status_code == 200 and r.text.strip().startswith("{"):
            OUT.joinpath(f"legacy_{label}.json").write_text(r.text, encoding="utf-8")
            payload = r.json()
            table1 = payload.get("Table1") or []
            print(label, "stores", len(table1), "rowcount", payload.get("Table"))


def main() -> None:
    with httpx.Client(timeout=30, follow_redirects=True) as client:
        try_fetch(client, "desktop", UA)
        try_fetch(client, "mobile", MOBILE_UA)


if __name__ == "__main__":
    main()
