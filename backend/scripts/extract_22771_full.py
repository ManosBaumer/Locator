from pathlib import Path

t = Path(__file__).resolve().parent.joinpath("kfc_probe_out", "app.86ae5fef.js").read_text(
    encoding="utf-8", errors="ignore"
)
start = t.find('"22771":function')
end = t.find('"63954":function', start)
Path(__file__).resolve().parent.joinpath("kfc_probe_out", "module_22771_full.txt").write_text(
    t[start:end], encoding="utf-8"
)
print("len", end - start)
