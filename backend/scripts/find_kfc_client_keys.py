import re
from pathlib import Path

text = Path(__file__).resolve().parent.joinpath("kfc_probe_out", "app.86ae5fef.js").read_text(
    encoding="utf-8", errors="ignore"
)

# likely client keys: kb + alphanumeric 14-20 chars
candidates = sorted(set(re.findall(r"kb[a-zA-Z0-9]{10,20}", text)))
print("kb* candidates", len(candidates))
for c in candidates[:30]:
    print(c)

# configs object literals with client
for m in re.finditer(r"\{[^{}]{0,200}client_key[^{}]{0,200}\}", text):
    s = m.group(0)
    if "client_sec" in s or "sec" in s:
        print("block", s[:300])
        break

# search for web-specific keys in 6202.js too
for fname in ["6202.js", "app.86ae5fef.js"]:
    t = Path(__file__).resolve().parent.joinpath("kfc_probe_out", fname).read_text(
        encoding="utf-8", errors="ignore"
    )
    for pat in [r"client_key:\s*\"([^\"]+)\"", r"client_sec:\s*\"([^\"]+)\""]:
        hits = re.findall(pat, t)
        if hits:
            print(fname, pat, hits[:5])
