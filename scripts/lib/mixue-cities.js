/**
 * Prefecture-level city centers for mainland China (Amap district API).
 * Cached to data/mixue-city-centers.json so later runs skip ~35s of API calls.
 */

const fs = require("fs");
const path = require("path");

const REPO_ROOT = path.resolve(__dirname, "../..");
const CACHE_PATH = path.join(REPO_ROOT, "data/mixue-city-centers.json");
const AMAP_DISTRICT = "https://restapi.amap.com/v3/config/district";

const EXCLUDED_PREFIXES = ["台湾", "台灣", "香港", "澳门", "澳門"];

function loadDotEnv() {
  const envPath = path.join(REPO_ROOT, ".env");
  if (!fs.existsSync(envPath)) return;
  for (const line of fs.readFileSync(envPath, "utf8").split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) continue;
    const eq = trimmed.indexOf("=");
    if (eq <= 0) continue;
    const key = trimmed.slice(0, eq);
    if (!process.env[key]) process.env[key] = trimmed.slice(eq + 1);
  }
}

function shortRegionName(name) {
  for (const suffix of ["特别行政区", "自治区", "自治州", "地区", "盟", "省", "市"]) {
    if (name.endsWith(suffix) && name.length > suffix.length) {
      return name.slice(0, -suffix.length);
    }
  }
  return name;
}

function parseCenter(center) {
  if (!center || !center.includes(",")) return null;
  const [lngStr, latStr] = center.split(",");
  const lat = Number(latStr);
  const lng = Number(lngStr);
  if (!Number.isFinite(lat) || !Number.isFinite(lng)) return null;
  return { lat, lng };
}

function isExcludedRegion(name) {
  return EXCLUDED_PREFIXES.some((p) => name.startsWith(p));
}

function cityKey(provinceShort, cityName) {
  return `${provinceShort}|${cityName}`;
}

async function fetchFromAmap(apiKey) {
  const centers = [];
  const response = await fetch(
    `${AMAP_DISTRICT}?key=${apiKey}&keywords=${encodeURIComponent("中国")}&subdistrict=1&extensions=base`
  );
  const payload = await response.json();
  if (payload.status !== "1") {
    throw new Error(`Amap district lookup failed: ${payload.info || payload.status}`);
  }

  const provinces = payload.districts?.[0]?.districts || [];
  for (const province of provinces) {
    const provinceName = province.name;
    if (!provinceName || isExcludedRegion(provinceName)) continue;
    const provinceShort = shortRegionName(provinceName);

    await new Promise((r) => setTimeout(r, 25));
    const cityResponse = await fetch(
      `${AMAP_DISTRICT}?key=${apiKey}&keywords=${encodeURIComponent(provinceName)}&subdistrict=1&extensions=base`
    );
    const cityPayload = await cityResponse.json();
    if (cityPayload.status !== "1") continue;

    const cityNodes = cityPayload.districts?.[0]?.districts || [];
    if (cityNodes.length > 0) {
      for (const city of cityNodes) {
        const coords = parseCenter(city.center);
        if (!city.name || !coords) continue;
        centers.push({
          key: cityKey(provinceShort, city.name),
          province: provinceShort,
          name: city.name,
          lat: coords.lat,
          lng: coords.lng,
        });
      }
      continue;
    }

    const coords = parseCenter(province.center);
    if (coords) {
      centers.push({
        key: cityKey(provinceShort, provinceName),
        province: provinceShort,
        name: provinceName,
        lat: coords.lat,
        lng: coords.lng,
      });
    }
  }

  centers.sort((a, b) => a.key.localeCompare(b.key, "zh"));
  return centers;
}

async function loadCityCenters({ refresh = false } = {}) {
  if (!refresh && fs.existsSync(CACHE_PATH)) {
    return JSON.parse(fs.readFileSync(CACHE_PATH, "utf8"));
  }

  loadDotEnv();
  const apiKey = process.env.AMAP_API_KEY;
  if (!apiKey) {
    throw new Error("AMAP_API_KEY missing in .env (needed to load prefecture city centers)");
  }

  console.log("Fetching prefecture city centers from Amap...");
  const centers = await fetchFromAmap(apiKey);
  fs.mkdirSync(path.dirname(CACHE_PATH), { recursive: true });
  fs.writeFileSync(CACHE_PATH, JSON.stringify(centers, null, 2));
  console.log(`Cached ${centers.length} cities → ${path.relative(REPO_ROOT, CACHE_PATH)}`);
  return centers;
}

function filterCitiesByBbox(cities, bbox) {
  if (!bbox) return cities;
  return cities.filter(
    (c) =>
      c.lat >= bbox.minLat &&
      c.lat <= bbox.maxLat &&
      c.lng >= bbox.minLng &&
      c.lng <= bbox.maxLng
  );
}

module.exports = {
  loadCityCenters,
  filterCitiesByBbox,
  cityKey,
  CACHE_PATH,
};
