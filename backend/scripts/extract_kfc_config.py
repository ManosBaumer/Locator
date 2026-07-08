from pathlib import Path

t = Path(__file__).resolve().parent.joinpath("kfc_probe_out", "app.86ae5fef.js").read_text(
    encoding="utf-8", errors="ignore"
)
for s in ["defaultApiName", "kfcPreDomain", "getCommonParams"]:
    idx = 0
    n = 0
    while n < 4:
        i = t.find(s, idx)
        if i < 0:
            break
        print("---", s, i)
        print(t[i : i + 400])
        idx = i + len(s)
        n += 1
