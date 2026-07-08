import re
from pathlib import Path

text = Path(__file__).resolve().parent.joinpath("kfc_probe_out", "app.86ae5fef.js").read_text(
    encoding="utf-8", errors="ignore"
)

for needle in ["configs", "kbsInfo", "client_sec", "getConfig", "bootstrap", "initConfig", "/config"]:
    print(f"\n=== {needle} count={text.count(needle)} ===")
    n = 0
    for m in re.finditer(re.escape(needle), text):
        snippet = text[max(0, m.start()-60):m.end()+120].replace("\n", " ")
        if "client" in snippet or "config" in snippet.lower() or "/config" in snippet:
            print(snippet[:220])
            n += 1
            if n >= 5:
                break
