import re
from pathlib import Path

text = Path(__file__).resolve().parent.joinpath("kfc_probe_out", "app.86ae5fef.js").read_text(
    encoding="utf-8", errors="ignore"
)

# kbsInfo blocks
for m in re.finditer(r"kbsInfo[^\}]{0,400}", text):
    snippet = m.group(0)
    if "client" in snippet:
        print(snippet[:400])
        print("---")

# search for hardcoded client keys (32+ char hex/alnum)
for m in re.finditer(r'client_key["\']?\s*[:=]\s*["\']([a-zA-Z0-9_-]{8,})["\']', text):
    print("key", m.group(1))

Path(__file__).resolve().parent.joinpath("kfc_probe_out", "kbs_snippets.txt").write_text(
    "\n\n".join(m.group(0) for m in re.finditer(r'.{0,200}kbsInfo.{0,400}', text)),
    encoding="utf-8",
)
print("written kbs_snippets.txt")
