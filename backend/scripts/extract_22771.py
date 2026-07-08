from pathlib import Path

t = Path(__file__).resolve().parent.joinpath("kfc_probe_out", "app.86ae5fef.js").read_text(
    encoding="utf-8", errors="ignore"
)
out = Path(__file__).resolve().parent / "kfc_probe_out"
m = t.find('"22771":function')
out.joinpath("module_22771.txt").write_text(t[m : m + 5000], encoding="utf-8")
idx = t.find('"Ju":function', m, m + 50000)
out.joinpath("Ju_fn.txt").write_text(t[idx : idx + 2000], encoding="utf-8")
print("ok")
