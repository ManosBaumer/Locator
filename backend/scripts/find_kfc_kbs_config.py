import re
from pathlib import Path

text = Path(__file__).resolve().parent.joinpath("kfc_probe_out", "app.86ae5fef.js").read_text(
    encoding="utf-8", errors="ignore"
)

# hardcoded secrets near kbsInfo
for m in re.finditer(r"kbsInfo", text):
    snippet = text[m.start() - 300 : m.start() + 500]
    if "client" in snippet and ("sec" in snippet or "key" in snippet):
        Path(__file__).resolve().parent.joinpath("kfc_probe_out", "kbs_context.txt").write_text(
            snippet, encoding="utf-8"
        )
        print("wrote first kbsInfo context")
        break

# find config load URL
for pat in (
    r"https://[^\"']+config[^\"']*",
    r"/api/v2/[^\"']+init[^\"']*",
    r"getConfigs[^\"']{0,120}",
):
    hits = sorted(set(re.findall(pat, text, re.I)))
    print(pat, len(hits))
    for h in hits[:15]:
        print(" ", h[:140])

# literal client_key strings (16 char alphanumeric after kb)
for m in re.finditer(r'"client_key"\s*:\s*"([^"]+)"', text):
    print("literal client_key", m.group(1))
for m in re.finditer(r'"client_sec"\s*:\s*"([^"]+)"', text):
    print("literal client_sec", m.group(1))
