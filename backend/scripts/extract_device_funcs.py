from pathlib import Path

t = Path(__file__).resolve().parent.joinpath("kfc_probe_out", "module_22771_full.txt").read_text(
    encoding="utf-8"
)
out = Path(__file__).resolve().parent / "kfc_probe_out"
for pat in ["getDeviceId=function", "getClientVersion=function", "getPortalSource=function"]:
    i = t.find(pat)
    print(pat, i)
    if i >= 0:
        name = pat.split("=")[0]
        out.joinpath(f"{name}.txt").write_text(t[i : i + 1500], encoding="utf-8")
