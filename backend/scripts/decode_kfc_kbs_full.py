import base64
import json
import re
from pathlib import Path

text = Path(__file__).resolve().parent.joinpath("kfc_probe_out", "app.86ae5fef.js").read_text(
    encoding="utf-8", errors="ignore"
)
m = re.search(r'"kbsInfo":\[(.*?)\]', text)
parts = re.findall(r'"([^"]*)"', m.group(1))
raw = "".join(parts).rstrip("$")
# pad base64
pad = (-len(raw)) % 4
raw_padded = raw + ("=" * pad)
data = json.loads(base64.b64decode(raw_padded).decode("utf-8"))
for entry in data:
    print(entry[0], entry[1])
