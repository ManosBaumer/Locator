from pathlib import Path

t = Path(__file__).resolve().parent.joinpath("kfc_probe_out", "app.86ae5fef.js").read_text(
    encoding="utf-8", errors="ignore"
)
# find store service exec
idx = t.find('"key":"exec"')
if idx < 0:
    idx = t.find('"exec",value:')
print("idx", idx)
for marker in ['"exec","value":', "key:\"exec\"", '.exec=function']:
    i = 0
    count = 0
    while count < 3:
        i = t.find(marker, i)
        if i < 0:
            break
        print("---", marker, i)
        print(t[i : i + 1200])
        i += len(marker)
        count += 1
