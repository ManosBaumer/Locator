import re
from pathlib import Path

text = Path(__file__).resolve().parent.joinpath("kfc_probe_out", "app.86ae5fef.js").read_text(
    encoding="utf-8", errors="ignore"
)

for needle in ["nY:function", '"nY"', "signaturePostCode", "forMD5", "stringToMD5"]:
    idx = 0
    n = 0
    while True:
        i = text.find(needle, idx)
        if i < 0:
            break
        print(f"\n=== {needle} @ {i} ===")
        print(text[i : i + 400])
        idx = i + 1
        n += 1
        if n >= 2:
            break

# find initSession API call body
i = text.find("/api/v2/init/initSession")
print("\ninitSession", text[i - 100 : i + 300])
