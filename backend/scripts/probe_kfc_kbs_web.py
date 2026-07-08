"""Test KFC order portal with correct KBS signing (WEB keys)."""

from __future__ import annotations

import hashlib
import json
import time
from urllib.parse import urlencode

from pathlib import Path

import httpx

BASE = "https://order.kfc.com.cn/preorder-portal"
CLIENT_KEY = "kbwapzJAAUs1g2od"
CLIENT_SEC = "fegFLVMJJ88If2hp"

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def md5(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def params_to_query_string(params: dict, encode: bool = False) -> str:
    """Mirror JS paramsToQueryString with sorted keys (encode=False for signing)."""

    def encode_val(v: object) -> str:
        s = "" if v is None else str(v)
        from urllib.parse import quote

        return quote(s, safe="") if encode else s

    def encode_key(k: str) -> str:
        from urllib.parse import quote

        return quote(k, safe="") if encode else k

    parts: list[str] = []

    def build(prefix: str, value: object, depth: int = 0) -> None:
        if depth > 20:
            raise ValueError("max depth")
        if value is None:
            parts.append(f"{prefix}=")
            return
        if isinstance(value, bool):
            parts.append(f"{prefix}={encode_val(str(value).lower())}")
            return
        if isinstance(value, (str, int, float)):
            parts.append(f"{prefix}={encode_val(value)}")
            return
        if isinstance(value, list):
            for i, item in enumerate(value):
                key = f"{prefix}[{i}]" if prefix else encode_key(str(i))
                build(key, item, depth + 1)
            return
        if isinstance(value, dict):
            for k in sorted(value.keys(), key=lambda x: str(x)):
                key = encode_key(k) if not prefix else f"{prefix}[{encode_key(k)}]"
                build(key, value[k], depth + 1)
            return
        parts.append(f"{prefix}={encode_val(str(value))}")

    for k in sorted(params.keys(), key=lambda x: str(x)):
        build(encode_key(k), params[k])
    return "&".join(parts)


def sign_get(path: str, query_params: dict | None = None) -> dict[str, str]:
    ts = str(int(time.time() * 1000))
    query = params_to_query_string(query_params or {}, encode=False)
    raw = f"{CLIENT_KEY}\t{CLIENT_SEC}\t{ts}\t{path}\t{query}"
    return {"kbcts": ts, "kbck": CLIENT_KEY, "kbsv": md5(raw)}


def sign_post(path: str, params: dict) -> tuple[dict[str, str], str]:
    ts = str(int(time.time() * 1000))
    body = json.dumps(params, separators=(",", ":"), ensure_ascii=False)
    raw = f"{CLIENT_KEY}\t{CLIENT_SEC}\t{ts}\t{path}\t\t{body}"
    return {"kbcts": ts, "kbck": CLIENT_KEY, "kbsv": md5(raw)}, body


def main() -> None:
    headers = {
        "User-Agent": UA,
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://order.kfc.com.cn/preorder-taro/home",
        "Origin": "https://order.kfc.com.cn",
    }
    with httpx.Client(timeout=30, headers=headers, follow_redirects=True) as client:
        # Warm up session
        client.get("https://order.kfc.com.cn/preorder-taro/home")

        path = "/api/v2/city/cities"
        sign = sign_get(path)
        r = client.get(BASE + path, headers=sign)
        out = Path(__file__).resolve().parent / "kfc_probe_out"
        out.mkdir(exist_ok=True)
        out.joinpath("cities_web2.json").write_text(r.text, encoding="utf-8")
        print("cities", r.status_code, len(r.text))

        path = "/api/v2/store/searchByCityCodeAndKeyword"
        params = {
            "gbCityCode": "110100",
            "keyword": "",
            "pageIndex": 1,
            "pageSize": 50,
            "mylatPhone": "",
            "mylngPhone": "",
        }
        sign, body = sign_post(path, params)
        r = client.post(
            BASE + path,
            headers={**sign, "Content-Type": "application/json"},
            content=body.encode("utf-8"),
        )
        out.joinpath("stores_web2.json").write_text(r.text, encoding="utf-8")
        print("stores", r.status_code, len(r.text))


if __name__ == "__main__":
    main()
