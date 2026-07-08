import re
from pathlib import Path

text = Path(__file__).resolve().parent.joinpath("kfc_probe_out", "app.86ae5fef.js").read_text(
    encoding="utf-8", errors="ignore"
)

for m in re.finditer(r"kbsInfo:\{[^\}]{0,800}\}", text):
    print(m.group(0)[:800])
    print("---")

for m in re.finditer(r"configs:\{[^\}]{0,200}kbsInfo", text):
    print("configs block", m.group(0)[:400])

# initSession
idx = text.find("initSession")
print("\ninitSession context:", text[idx:idx+400])
