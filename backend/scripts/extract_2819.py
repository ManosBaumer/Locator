from pathlib import Path

t = Path(__file__).resolve().parent.joinpath("kfc_probe_out", "app.86ae5fef.js").read_text(
    encoding="utf-8", errors="ignore"
)
out = Path(__file__).resolve().parent / "kfc_probe_out"
m = t.find('"2819":function')
out.joinpath("module_2819.txt").write_text(t[m : m + 4000], encoding="utf-8")
print("ok", m)
