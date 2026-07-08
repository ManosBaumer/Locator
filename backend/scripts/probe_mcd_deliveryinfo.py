import re

import httpx
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.mcdonalds.com.cn/"}
BASE = "https://www.mcdonalds.com.cn/index/Services/publicinfo/deliveryinfo"


def fetch_page(page: int) -> str:
    r = httpx.get(BASE, params={"page": page}, headers=HEADERS, timeout=30, follow_redirects=True)
    r.raise_for_status()
    return r.text


def parse_stores(html: str) -> list[tuple[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    rows = []
    for tr in soup.select("table tr")[1:]:
        cells = [c.get_text(" ", strip=True) for c in tr.find_all("td")]
        if len(cells) >= 2:
            rows.append((cells[0], cells[1]))
    return rows


def max_page(html: str) -> int | None:
    nums = [int(x) for x in re.findall(r">\s*(\d+)\s*<", html) if int(x) < 10000]
    return max(nums) if nums else None


def main() -> None:
    html1 = fetch_page(1)
    stores1 = parse_stores(html1)
    print("page1 stores", len(stores1))
    print("sample", stores1[:3])
    print("max page hint", max_page(html1))

    html812 = fetch_page(812)
    stores812 = parse_stores(html812)
    print("page812 stores", len(stores812))
    if stores812:
        print("page812 sample", stores812[:2])

    # estimate total by sampling last pages
    total = 0
    for p in (1, 2, 811, 812):
        total += len(parse_stores(fetch_page(p)))
    print("sampled count from 4 pages", total)
    est = len(stores1) * max_page(html1) if max_page(html1) else None
    print("rough est if ~10/page", est)


if __name__ == "__main__":
    main()
