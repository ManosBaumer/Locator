from pathlib import Path

t = Path(__file__).resolve().parent.joinpath("kfc_probe_out", "app.86ae5fef.js").read_text(
    encoding="utf-8", errors="ignore"
)
m = t.find('"10319":function')
print("module at", m)
print(t[m : m + 2500])
