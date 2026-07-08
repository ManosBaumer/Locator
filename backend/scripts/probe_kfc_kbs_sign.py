"""Test KFC preorder-portal API with KBS signing."""

from __future__ import annotations

import hashlib
import json
import time

import httpx

BASE = "https://order.kfc.com.cn/preorder-portal"
# From public reverse-engineering of Yum China mobile SDK (may differ for web).
CLIENT_KEY = "kbappkwle8K1Mhlc"
CLIENT_SEC = "WYjEbpFholuphDuO"

UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148"
)


def md5(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def sign_get(path: str, query: str = "") -> dict[str, str]:
    ts = str(int(time.time() * 1000))
    raw = f"{CLIENT_KEY}\t{CLIENT_SEC}\t{ts}\t{path}\t{query}"
    return {"kbcts": ts, "kbck": CLIENT_KEY, "kbsv": md5(raw)}


def sign_post(path: str, body: str) -> dict[str, str]:
    ts = str(int(time.time() * 1000))
    raw = f"{CLIENT_KEY}\t{CLIENT_SEC}\t{ts}\t{path}\t\t{body}"
    return {"kbcts": ts, "kbck": CLIENT_KEY, "kbsv": md5(raw)}


def main() -> None:
    headers = {
        "User-Agent": UA,
        "Accept": "application/json",
        "Referer": "https://order.kfc.com.cn/",
        "Origin": "https://order.kfc.com.cn",
    }
    with httpx.Client(timeout=30, headers=headers, follow_redirects=True) as client:
        for path in (
            "/api/v2/city/cities",
            "/api/v2/store/searchByCityCodeAndKeyword",
        ):
            sign = sign_get(path, "")
            r = client.get(BASE + path, headers=sign)
            print("GET", path, r.status_code, r.text[:300])
            if path.endswith("searchByCityCodeAndKeyword"):
                continue
        # POST search with empty keyword for a city
        path = "/api/v2/store/searchByCityCodeAndKeyword"
        params = {"gbCityCode": "110100", "keyword": "", "pageIndex": 1, "pageSize": 50}
        body = json.dumps(params, separators=(",", ":"), ensure_ascii=False)
        sign = sign_post(path, body)
        r = client.post(
            BASE + path,
            headers={**sign, "Content-Type": "application/json"},
            content=body.encode("utf-8"),
        )
        print("POST search", r.status_code, r.text[:500])


if __name__ == "__main__":
    main()
