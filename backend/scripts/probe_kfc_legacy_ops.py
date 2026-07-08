"""Try all legacy KFC GetStoreList op variants."""

from __future__ import annotations

from pathlib import Path

import httpx

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
BASE = "http://www.kfc.com.cn/kfccda/ashx/GetStoreList.ashx"
OUT = Path(__file__).resolve().parent / "kfc_probe_out"


def main() -> None:
    OUT.mkdir(exist_ok=True)
    headers = {
        "User-Agent": UA,
        "Referer": "http://www.kfc.com.cn/kfccda/storelist/index.aspx",
        "Origin": "http://www.kfc.com.cn",
        "X-Requested-With": "XMLHttpRequest",
    }
    with httpx.Client(timeout=30, headers=headers, follow_redirects=True) as client:
        client.get("http://www.kfc.com.cn/")
        for op in ("cname", "keyword", "pid", "province", "city"):
            for qs in (f"?op={op}", f"?op={op}&v=1"):
                url = BASE + qs
                payloads = [
                    {"cname": "北京", "pid": "", "pageIndex": "1", "pageSize": "5"},
                    {"cname": "", "pid": "", "keyword": "北京", "pageIndex": "1", "pageSize": "5"},
                    {"keyword": "北京", "pageIndex": "1", "pageSize": "5"},
                ]
                for data in payloads:
                    r = client.post(url, data=data)
                    ok = r.status_code == 200 and r.text.strip().startswith("{")
                    print(op, qs, data, r.status_code, "OK" if ok else r.text[:60])
                    if ok:
                        OUT.joinpath(f"legacy_{op}.json").write_text(r.text, encoding="utf-8")
                        return


if __name__ == "__main__":
    main()
