from pathlib import Path

t = Path(__file__).resolve().parent.joinpath("kfc_probe_out", "app.86ae5fef.js").read_text(
    encoding="utf-8", errors="ignore"
)
out = Path(__file__).resolve().parent / "kfc_probe_out"
# module 9165
m = t.find('"9165":function')
out.joinpath("module_9165.txt").write_text(t[m : m + 5000], encoding="utf-8")
# getBaseUrl in store module
idx = t.find("getBaseUrl", 1068000)
out.joinpath("getBaseUrl.txt").write_text(t[idx : idx + 2000], encoding="utf-8")
print("ok")
