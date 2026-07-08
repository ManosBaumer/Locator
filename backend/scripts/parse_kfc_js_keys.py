import re
from pathlib import Path

text = Path(__file__).resolve().parent.joinpath("kfc_probe_out", "app.86ae5fef.js").read_text(
    encoding="utf-8", errors="ignore"
)

for needle in ["client_key", "clientKey", "baseURL", "preorder-portal", "common/cities", "gbCityCode", "cityCode"]:
    hits = list(re.finditer(re.escape(needle), text))
    print(needle, len(hits))
    if hits:
        m = hits[0]
        print(text[max(0, m.start()-80):m.end()+120].replace("\n", " ")[:260])

# find searchByCityCodeAndKeyword params usage in store list page chunk
idx = text.find("storeList")
print("\nstoreList idx", idx)
if idx >= 0:
    print(text[idx:idx+500][:500])
