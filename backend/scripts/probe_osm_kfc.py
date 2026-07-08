import httpx

query = r"""
[out:json][timeout:120];
area["ISO3166-1"="CN"]["admin_level"="2"]->.cn;
(
  node["brand"="KFC"](area.cn);
  node["brand:en"="KFC"](area.cn);
  node["name"~"肯德基",i]["amenity"="fast_food"](area.cn);
  way["brand"="KFC"](area.cn);
  way["name"~"肯德基",i]["amenity"="fast_food"](area.cn);
);
out center 5;
"""

r = httpx.post(
    "https://overpass-api.de/api/interpreter",
    data={"data": query},
    timeout=180,
)
print("status", r.status_code, "bytes", len(r.content))
data = r.json()
elements = data.get("elements") or []
print("sample count header", len(elements))
# get total via separate count query
count_q = r"""
[out:json][timeout:120];
area["ISO3166-1"="CN"]["admin_level"="2"]->.cn;
(
  node["brand"="KFC"](area.cn);
  node["name"~"肯德基",i]["amenity"="fast_food"](area.cn);
);
out count;
"""
r2 = httpx.post("https://overpass-api.de/api/interpreter", data={"data": count_q}, timeout=180)
print("count response", r2.text[:300])
if elements:
    e = elements[0]
    print("sample", e.get("tags", {}), e.get("lat"), e.get("lon"))
