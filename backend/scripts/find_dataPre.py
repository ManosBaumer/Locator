import re
from pathlib import Path

text = Path(__file__).resolve().parent.joinpath("kfc_probe_out", "app.86ae5fef.js").read_text(
    encoding="utf-8", errors="ignore"
)

for needle in ["dataPre", "kfc-ordering-preorder", "client_sec", "client_key"]:
    if needle == "client_key":
        # find all quoted strings near client_key in dataPre context
        for m in re.finditer(r"dataPre", text):
            snippet = text[m.start() : m.start() + 2000]
            if "client_key" in snippet:
                Path(__file__).resolve().parent.joinpath("kfc_probe_out", "dataPre_snip.txt").write_text(
                    snippet, encoding="utf-8"
                )
                print("wrote dataPre_snip with client_key")
                break
    else:
        idx = text.find(needle)
        print(needle, "first idx", idx)

# search entire file for client_sec literal
secs = re.findall(r'client_sec:"([A-Za-z0-9]{8,20})"', text)
keys = re.findall(r'client_key:"([A-Za-z0-9]{8,20})"', text)
print("literal keys", keys[:20])
print("literal secs", secs[:20])
