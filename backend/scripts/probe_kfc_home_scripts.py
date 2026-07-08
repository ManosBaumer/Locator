"""Probe KFC homepage for embedded store API config."""

from __future__ import annotations

import json
import re
from pathlib import Path

import httpx

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
OUT = Path(__file__).resolve().parent / "kfc_probe_out"


def main() -> None:
    OUT.mkdir(exist_ok=True)
    urls = [
        "https://www.kfc.com.cn/",
        "http://www.kfc.com.cn/",
        "https://m.kfc.com.cn/",
    ]
    with httpx.Client(timeout=30, headers={"User-Agent": UA}, follow_redirects=True) as c:
        for url in urls:
            r = c.get(url)
            text = r.text
            OUT.joinpath(f"home_{url.split('//')[1].replace('/','_')}.html").write_text(
                text[:200000], encoding="utf-8", errors="ignore"
            )
            patterns = [
                r"GetStoreList[^\"']*",
                r"storelist[^\"']*",
                r"preorder-portal[^\"']*",
                r"api/v2/[^\"']*",
                r"runtimeConfig[^}]+}",
                r"storesDomain[^\"']*",
            ]
            print(url, r.status_code, len(text))
            for pat in patterns:
                hits = sorted(set(re.findall(pat, text, re.I)))[:10]
                if hits:
                    print(" ", pat, hits)


if __name__ == "__main__":
    main()
