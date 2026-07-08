from pathlib import Path

t = Path(__file__).resolve().parent.joinpath("kfc_probe_out", "app.86ae5fef.js").read_text(
    encoding="utf-8", errors="ignore"
)
m = t.find('"77630":function')
Path(__file__).resolve().parent.joinpath("kfc_probe_out", "module_77630.txt").write_text(
    t[m : m + 15000], encoding="utf-8"
)
print("ok", m)
