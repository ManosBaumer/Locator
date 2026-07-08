import re
import httpx
from pathlib import Path

OUT = Path(__file__).resolve().parent / "kfc_probe_out"
OUT.mkdir(exist_ok=True)

UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148"
)

for url in (
    "https://order.kfc.com.cn/",
    "https://order.kfc.com.cn/preorder-portal/",
    "https://order.kfc.com.cn/preorder-portal/index.html",
):
    r = httpx.get(url, headers={"User-Agent": UA}, timeout=30, follow_redirects=True)
    path = OUT / ("order_" + url.split("//")[1].replace("/", "_") + ".html")
    path.write_text(r.text, encoding="utf-8")
    print(url, r.status_code, len(r.text))
    for js in re.findall(r'src="([^"]+\.js[^"]*)"', r.text):
        print(" js", js[:120])
    for hit in sorted(set(re.findall(r"/preorder-portal/api/[^\"'\\s<>]+", r.text))):
        print(" api", hit)
