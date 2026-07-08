from pathlib import Path

t = Path(__file__).resolve().parent.joinpath("kfc_probe_out", "app.86ae5fef.js").read_text(
    encoding="utf-8", errors="ignore"
)
out = Path(__file__).resolve().parent / "kfc_probe_out"
m = t.find('"20422":function')
out.joinpath("module_20422.txt").write_text(t[m : m + 6000], encoding="utf-8")
# Pe.sj = getCommonParams for store module
m2 = t.find('"sj":function')
out.joinpath("Pe_sj.txt").write_text(t[m2 : m2 + 2500], encoding="utf-8")
print("written")
