import re
from pathlib import Path

text = Path(__file__).resolve().parent.joinpath("kfc_probe_out", "app.86ae5fef.js").read_text(
    encoding="utf-8", errors="ignore"
)
patterns = [
    r"api/v2/store/[a-zA-Z0-9/_-]+",
    r"api/v2/city/[a-zA-Z0-9/_-]+",
    r"store/[a-zA-Z0-9/_-]+",
]
for pat in patterns:
    hits = sorted(set(re.findall(pat, text)))
    print(pat, len(hits))
    for h in hits:
        print(" ", h)

# context around city/cities
for m in re.finditer(r"city/cities", text):
    start = max(0, m.start() - 120)
    end = min(len(text), m.end() + 120)
    print("\ncontext city/cities:", text[start:end].replace("\n", " ")[:240])
    break

for m in re.finditer(r"store/list", text):
    start = max(0, m.start() - 120)
    end = min(len(text), m.end() + 120)
    print("\ncontext store/list:", text[start:end].replace("\n", " ")[:240])
    break
