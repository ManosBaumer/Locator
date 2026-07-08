from pathlib import Path

t = Path(__file__).resolve().parent.joinpath("kfc_probe_out", "app.86ae5fef.js").read_text(
    encoding="utf-8", errors="ignore"
)
out = Path(__file__).resolve().parent / "kfc_probe_out"
m = t.find('"18536":function')
out.joinpath("module_18536_full.txt").write_text(t[m : m + 8000], encoding="utf-8")
print("ok")
