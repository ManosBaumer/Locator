import re
from pathlib import Path

text = Path(__file__).resolve().parent.joinpath("kfc_probe_out", "app.86ae5fef.js").read_text(
    encoding="utf-8", errors="ignore")

# extract module 17187
m = re.search(r'"17187":function\(ee,ce,le\)\{(.+?)\},"17188":', text)
if m:
    mod = m.group(1)[:4000]
    Path(__file__).resolve().parent.joinpath("kfc_probe_out", "module_17187.js").write_text(mod, encoding="utf-8")
    print("module 17187 len", len(m.group(1)))
else:
    print("module not found")
    # try alternate pattern
    idx = text.find('"17187":function')
    print(text[idx:idx+2000][:2000])
