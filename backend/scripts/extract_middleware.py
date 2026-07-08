from pathlib import Path

t = Path(__file__).resolve().parent.joinpath("kfc_probe_out", "app.86ae5fef.js").read_text(
    encoding="utf-8", errors="ignore"
)
out = Path(__file__).resolve().parent / "kfc_probe_out"
for mod in ["44185", "39451", "93068"]:
    m = t.find(f'"{mod}":function')
    out.joinpath(f"module_{mod}.txt").write_text(t[m : m + 3500], encoding="utf-8")
    print(mod, m)
