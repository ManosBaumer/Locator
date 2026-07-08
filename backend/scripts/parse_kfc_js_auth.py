import re
from pathlib import Path

text = Path(__file__).resolve().parent.joinpath("kfc_probe_out", "app.86ae5fef.js").read_text(
    encoding="utf-8", errors="ignore"
)

needles = [
    "searchByCityCodeAndKeyword",
    "searchByLbs",
    "city/cities",
    "kbck",
    "kbsv",
    "exec({",
    "fiveLayer",
    "5层",
]
for needle in needles:
    print(f"\n=== {needle} ===")
    count = 0
    for m in re.finditer(re.escape(needle), text):
        start = max(0, m.start() - 100)
        end = min(len(text), m.end() + 200)
        snippet = text[start:end].replace("\n", " ")
        print(snippet[:280])
        count += 1
        if count >= 3:
            break
