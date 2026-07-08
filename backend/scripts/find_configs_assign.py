import re
from pathlib import Path

text = Path(__file__).resolve().parent.joinpath("kfc_probe_out", "app.86ae5fef.js").read_text(
    encoding="utf-8", errors="ignore"
)

# OB.configs assignments
for m in re.finditer(r"configs\s*=\s*\{", text):
    print(text[m.start() : m.start() + 600][:600])
    print("---")

for m in re.finditer(r"kbsInfo\s*:\s*\{", text):
    print("kbsInfo literal", text[m.start() : m.start() + 400][:400])
    print("---")
