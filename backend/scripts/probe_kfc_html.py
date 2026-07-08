import httpx
import re
from pathlib import Path

UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)
OUT = Path(__file__).resolve().parent / "kfc_probe_out"
OUT.mkdir(exist_ok=True)

for url in (
    "https://m.kfc.com.cn/store/",
    "https://www.kfc.com.cn/",
    "https://order.kfc.com.cn/preorder-portal/home",
):
    r = httpx.get(url, headers={"User-Agent": UA}, timeout=30, follow_redirects=True)
    path = OUT / (url.split("//")[1].replace("/", "_") + ".html")
    path.write_text(r.text, encoding="utf-8")
    print(url, r.status_code, len(r.text), "->", path.name)
    hits = set()
    for pat in (
        r"https?://[^\"'\\s<>]+",
        r"/(?:api|store|kfccda|preorder|ashx)[^\"'\\s<>]*",
        r"GetStoreList[^\"'\\s<>]*",
    ):
        hits.update(re.findall(pat, r.text, re.I))
    for h in sorted(hits):
        if any(k in h.lower() for k in ("store", "api", "ashx", "kfc", "city", "list")):
            print(" ", h[:160])
