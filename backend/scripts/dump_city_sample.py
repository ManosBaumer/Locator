import json
from pathlib import Path

data = json.loads(Path("scripts/kfc_probe_out/cities_correct.json").read_text(encoding="utf-8"))
Path("scripts/kfc_probe_out/city_sample.json").write_text(
    json.dumps(data["data"]["allCities"][:3], ensure_ascii=False, indent=2),
    encoding="utf-8",
)
