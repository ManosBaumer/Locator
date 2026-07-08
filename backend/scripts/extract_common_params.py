from pathlib import Path

t = Path(__file__).resolve().parent.joinpath("kfc_probe_out", "app.86ae5fef.js").read_text(
    encoding="utf-8", errors="ignore"
)
out = Path(__file__).resolve().parent / "kfc_probe_out" / "common_params.txt"
idx = t.find('"getCommonParams"')
out.write_text(t[idx : idx + 3500], encoding="utf-8")
print("written", idx)
