import json
import re
from pathlib import Path

t = Path(__file__).resolve().parent.joinpath("kfc_probe_out", "app.86ae5fef.js").read_text(
    encoding="utf-8", errors="ignore"
)
m = re.search(r'"77630":function\(ee\)\{"use strict";ee\.exports=JSON\.parse\(\'(\[.*?\})\'\)', t)
if not m:
    # fallback: read module file
    raw = Path(__file__).resolve().parent.joinpath("kfc_probe_out", "module_77630.txt").read_text(
        encoding="utf-8"
    )
    start = raw.find("[{")
    end = raw.rfind("}]") + 2
    data = json.loads(raw[start:end])
else:
    data = json.loads(m.group(1))

preorder_h5 = [x for x in data if x.get("businessLine") == "preorder" and x.get("client") == "h5"]
print("preorder h5 channels:", json.dumps(preorder_h5, ensure_ascii=False, indent=2))
print("count", len(preorder_h5))
