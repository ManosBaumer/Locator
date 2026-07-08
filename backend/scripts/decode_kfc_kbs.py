"""Decode obfuscated kbsInfo strings from KFC preorder JS bundle."""

from __future__ import annotations

import json
import re
from pathlib import Path

text = Path(__file__).resolve().parent.joinpath("kfc_probe_out", "app.86ae5fef.js").read_text(
    encoding="utf-8", errors="ignore"
)

# Extract obfuscated string arrays for config keys.
for key in ("kbsInfo", "mktInfo", "tdsdkAppkey", "ipsInfo"):
    m = re.search(rf'"{key}":\[(.*?)\]', text)
    if not m:
        print(key, "NOT FOUND")
        continue
    parts = re.findall(r'"([^"]*)"', m.group(1))
    decoded = "".join(parts)
    print(key, "parts", len(parts), "decoded", decoded)

# Also dump full Pn object snippet
m = re.search(r'Pn=\{(.*?)\},In=\{', text)
if m:
    Path(__file__).resolve().parent.joinpath("kfc_probe_out", "Pn_obj.txt").write_text(
        "Pn={" + m.group(1)[:8000] + "}", encoding="utf-8"
    )
    print("wrote Pn_obj.txt")
