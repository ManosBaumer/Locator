from pathlib import Path

t = Path(__file__).resolve().parent.joinpath("kfc_probe_out", "app.86ae5fef.js").read_text(
    encoding="utf-8", errors="ignore"
)
out = Path(__file__).resolve().parent / "kfc_probe_out"
for pat in ["FI:function", "ew:function", "pureBl", "getClientVersion=function"]:
    i = t.find(pat)
    print(pat, i)
    if i > 0:
        out.joinpath(f"ctx_{pat.replace(':','_')}.txt").write_text(t[i - 100 : i + 2000], encoding="utf-8")
