from pathlib import Path

t = Path(__file__).resolve().parent.joinpath("kfc_probe_out", "app.86ae5fef.js").read_text(
    encoding="utf-8", errors="ignore"
)
out = Path(__file__).resolve().parent / "kfc_probe_out"
# module containing cities at 1074676 - find class start
start = t.rfind("function(", 1068000, 1072000)
out.joinpath("store_module_start.txt").write_text(t[start : start + 4000], encoding="utf-8")
# find kfcPreDomain usage
idx = 0
hits = []
while len(hits) < 8:
    i = t.find("kfcPreDomain", idx)
    if i < 0:
        break
    hits.append(t[i - 200 : i + 500])
    idx = i + 12
out.joinpath("kfc_pre_domain_usage.txt").write_text("\n\n===\n\n".join(hits), encoding="utf-8")
print("done", len(hits))
