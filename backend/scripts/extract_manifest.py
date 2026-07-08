from pathlib import Path

text = Path(__file__).resolve().parent.joinpath("kfc_probe_out", "app.86ae5fef.js").read_text(
    encoding="utf-8", errors="ignore"
)
start = text.find('{"name":"kfc-ordering-preorder"')
chunk = text[start : start + 40000]
Path(__file__).resolve().parent.joinpath("kfc_probe_out", "manifest_chunk.txt").write_text(
    chunk, encoding="utf-8"
)
for kw in [
    "kbsInfo",
    "client_key",
    "client_sec",
    "configUrl",
    "remoteConfig",
    "res.kfc",
    "jsonFile",
    "kfcOrderingConfig",
]:
    if kw in chunk:
        i = chunk.find(kw)
        print(kw, chunk[i - 80 : i + 250])
