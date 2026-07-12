#!/usr/bin/env node
/**
 * HeyTea (喜茶) mainland store scraper — HeyTea GO app API (go.heytea.com).
 *
 * One POST per city (~303 calls); no grid crawl needed.
 *
 * Usage:
 *   node scripts/scrape-heytea.js
 *   node scripts/scrape-heytea.js --resume
 *   node scripts/scrape-heytea.js --export
 *   node scripts/scrape-heytea.js --test-shanghai
 *
 * Output:
 *   frontend/public/data/locations/heytea.geojson
 *   data/heytea-checkpoint.json
 */

const fs = require("fs");
const path = require("path");
const { fetchMainlandCities, fetchShopsForCity } = require("./lib/heytea-api");
const { gcj02ToWgs84 } = require("./lib/gcj02");

const REPO_ROOT = path.resolve(__dirname, "..");
const OUT_GEOJSON = path.join(REPO_ROOT, "frontend/public/data/locations/heytea.geojson");
const CHECKPOINT_PATH = path.join(REPO_ROOT, "data/heytea-checkpoint.json");
const CITIES_CACHE_PATH = path.join(REPO_ROOT, "data/heytea-cities.json");
const CHAINS_JSON = path.join(REPO_ROOT, "frontend/public/data/chains.json");
const MANIFEST_JSON = path.join(REPO_ROOT, "frontend/public/data/manifest.json");

const CHECKPOINT_VERSION = 1;
const DEFAULT_DELAY_MS = 50;
const CHAIN_SLUG = "heytea";
const CHAIN_NAME = "喜茶 / HeyTea";
const CATEGORY_SLUG = "tea-shop";

const MAINLAND_BBOX = {
  minLat: 17.5,
  maxLat: 54.5,
  minLng: 72,
  maxLng: 136,
};

function parseArgs(argv) {
  const args = {
    resume: false,
    exportOnly: false,
    testShanghai: false,
    delayMs: DEFAULT_DELAY_MS,
  };
  for (let i = 2; i < argv.length; i++) {
    const arg = argv[i];
    if (arg === "--resume") args.resume = true;
    else if (arg === "--export") args.exportOnly = true;
    else if (arg === "--test-shanghai") args.testShanghai = true;
    else if (arg === "--delay") args.delayMs = Number(argv[++i]);
    else if (arg === "--help" || arg === "-h") {
      console.log(`Usage: node scripts/scrape-heytea.js [options]

Options:
  --resume         Continue from data/heytea-checkpoint.json
  --export         Re-write geojson + manifest from checkpoint
  --test-shanghai  Crawl Shanghai only (city_code 156310000)
  --delay MS       Delay between city API calls (default ${DEFAULT_DELAY_MS})
`);
      process.exit(0);
    }
  }
  return args;
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function isHkOrMacao(cityCode) {
  const code = String(cityCode || "");
  return code.startsWith("15681") || code.startsWith("15682");
}

function isMainlandRetailShop(shop) {
  if (!shop || shop.is_overseas) return false;
  if (shop.is_enable === 0 || shop.is_enable === false) return false;
  const cityCode = shop.city_code || "";
  if (isHkOrMacao(cityCode)) return false;
  const lat = Number(shop.latitude);
  const lng = Number(shop.longitude);
  if (!Number.isFinite(lat) || !Number.isFinite(lng)) return false;
  if (
    lat < MAINLAND_BBOX.minLat ||
    lat > MAINLAND_BBOX.maxLat ||
    lng < MAINLAND_BBOX.minLng ||
    lng > MAINLAND_BBOX.maxLng
  ) {
    return false;
  }
  return true;
}

function shopNumericId(shopId) {
  let hash = 0;
  for (const ch of String(shopId)) {
    hash = (hash * 31 + ch.charCodeAt(0)) >>> 0;
  }
  return hash || 1;
}

function shopToFeature(shop) {
  const id = shopNumericId(shop.id);
  const gcjLng = Number(shop.longitude);
  const gcjLat = Number(shop.latitude);
  const [lng, lat] = gcj02ToWgs84(gcjLng, gcjLat);
  const cityLabel = [shop.province, shop.city, shop.district].filter(Boolean).join(" ");
  return {
    type: "Feature",
    id,
    geometry: { type: "Point", coordinates: [lng, lat] },
    properties: {
      id,
      name: shop.name,
      chain_slug: CHAIN_SLUG,
      category_slug: CATEGORY_SLUG,
      address: shop.address || null,
      city: cityLabel || shop.city || null,
      shop_id: shop.id,
    },
  };
}

function storesToGeojson(storesById) {
  const features = Object.values(storesById)
    .filter(isMainlandRetailShop)
    .map(shopToFeature)
    .sort((a, b) => a.id - b.id);
  return { type: "FeatureCollection", features };
}

function emptyCheckpoint() {
  return {
    version: CHECKPOINT_VERSION,
    stores: {},
    completedCityKeys: [],
    pendingCities: [],
    stats: { apiCalls: 0, citiesCompleted: 0, shopsAdded: 0 },
  };
}

function loadCheckpoint() {
  if (!fs.existsSync(CHECKPOINT_PATH)) {
    return emptyCheckpoint();
  }
  const cp = JSON.parse(fs.readFileSync(CHECKPOINT_PATH, "utf8"));
  if (cp.version !== CHECKPOINT_VERSION) {
    console.warn(`Checkpoint version ${cp.version} → resetting to v${CHECKPOINT_VERSION}`);
    return emptyCheckpoint();
  }
  cp.stores = cp.stores || {};
  cp.completedCityKeys = cp.completedCityKeys || [];
  cp.pendingCities = cp.pendingCities || [];
  cp.stats = cp.stats || emptyCheckpoint().stats;
  return cp;
}

function saveCheckpoint(checkpoint) {
  fs.mkdirSync(path.dirname(CHECKPOINT_PATH), { recursive: true });
  fs.writeFileSync(CHECKPOINT_PATH, JSON.stringify(checkpoint, null, 2));
}

function mergeShops(checkpoint, shops) {
  let added = 0;
  for (const shop of shops) {
    if (!isMainlandRetailShop(shop)) continue;
    const key = String(shop.id);
    if (!checkpoint.stores[key]) added += 1;
    checkpoint.stores[key] = shop;
  }
  return added;
}

function writeGeojson(storesById) {
  fs.mkdirSync(path.dirname(OUT_GEOJSON), { recursive: true });
  const payload = storesToGeojson(storesById);
  fs.writeFileSync(OUT_GEOJSON, JSON.stringify(payload));
  return payload.features.length;
}

function updateManifestAndChains(featureCount) {
  let chains = [];
  if (fs.existsSync(CHAINS_JSON)) {
    chains = JSON.parse(fs.readFileSync(CHAINS_JSON, "utf8"));
  }
  const existing = chains.find((c) => c.slug === CHAIN_SLUG);
  if (existing) {
    existing.location_count = featureCount;
    existing.name = CHAIN_NAME;
    existing.category_slug = CATEGORY_SLUG;
  } else {
    const maxId = chains.reduce((m, c) => Math.max(m, c.id || 0), 0);
    chains.push({
      id: maxId + 1,
      name: CHAIN_NAME,
      slug: CHAIN_SLUG,
      category_slug: CATEGORY_SLUG,
      location_count: featureCount,
    });
    chains.sort((a, b) => a.name.localeCompare(b.name));
  }
  fs.writeFileSync(CHAINS_JSON, JSON.stringify(chains, null, 2));

  let manifest = { chains: [], location_count: 0 };
  if (fs.existsSync(MANIFEST_JSON)) {
    manifest = JSON.parse(fs.readFileSync(MANIFEST_JSON, "utf8"));
  }
  manifest.chains = chains.map((c) => c.slug);
  manifest.location_count = chains.reduce((sum, c) => sum + (c.location_count || 0), 0);
  fs.writeFileSync(MANIFEST_JSON, JSON.stringify(manifest, null, 2));
}

async function loadOrFetchCities() {
  if (fs.existsSync(CITIES_CACHE_PATH)) {
    const cached = JSON.parse(fs.readFileSync(CITIES_CACHE_PATH, "utf8"));
    if (Array.isArray(cached) && cached.length > 0) {
      return cached;
    }
  }
  const cities = await fetchMainlandCities();
  fs.mkdirSync(path.dirname(CITIES_CACHE_PATH), { recursive: true });
  fs.writeFileSync(CITIES_CACHE_PATH, JSON.stringify(cities, null, 2));
  return cities;
}

function cityKey(city) {
  return city.city_code;
}

async function buildCityQueue(args, checkpoint) {
  if (args.testShanghai) {
    return [{ name: "上海市", city_code: "156310000" }];
  }
  const cities = await loadOrFetchCities();
  const completed = new Set(checkpoint.completedCityKeys || []);
  return cities.filter((c) => !completed.has(cityKey(c)));
}

async function crawlCities(args, checkpoint) {
  if (checkpoint.pendingCities.length === 0) {
    checkpoint.pendingCities = await buildCityQueue(args, checkpoint);
  }

  const total =
    checkpoint.stats.citiesCompleted + checkpoint.pendingCities.length;
  console.log(
    `HeyTea scrape: ${Object.keys(checkpoint.stores).length} stores, ` +
      `${checkpoint.stats.citiesCompleted}/${total} cities done, ` +
      `${checkpoint.pendingCities.length} pending`
  );

  while (checkpoint.pendingCities.length > 0) {
    const city = checkpoint.pendingCities.shift();
    const key = cityKey(city);
    const label = city.name || key;

    try {
      const shops = await fetchShopsForCity(city.city_code);
      checkpoint.stats.apiCalls += 1;
      const added = mergeShops(checkpoint, shops);
      checkpoint.stats.shopsAdded += added;
      checkpoint.completedCityKeys.push(key);
      checkpoint.stats.citiesCompleted += 1;

      if (
        checkpoint.stats.citiesCompleted % 10 === 0 ||
        checkpoint.pendingCities.length === 0
      ) {
        saveCheckpoint(checkpoint);
        const count = Object.keys(checkpoint.stores).length;
        process.stdout.write(
          `\r  ${checkpoint.stats.citiesCompleted}/${total} cities | ${count} stores | last: ${label} (+${added})   `
        );
      }
    } catch (err) {
      console.error(`\nFailed ${label}: ${err.message}`);
      checkpoint.pendingCities.unshift(city);
      saveCheckpoint(checkpoint);
      throw err;
    }

    if (args.delayMs > 0) {
      await sleep(args.delayMs);
    }
  }

  console.log("");
  saveCheckpoint(checkpoint);
}

async function run() {
  const args = parseArgs(process.argv);

  if (args.exportOnly) {
    const checkpoint = loadCheckpoint();
    const featureCount = writeGeojson(checkpoint.stores);
    updateManifestAndChains(featureCount);
    console.log(
      `Exported ${featureCount} stores → ${path.relative(REPO_ROOT, OUT_GEOJSON)}`
    );
    return;
  }

  const checkpoint = args.resume ? loadCheckpoint() : emptyCheckpoint();
  await crawlCities(args, checkpoint);
  const featureCount = writeGeojson(checkpoint.stores);
  updateManifestAndChains(featureCount);
  console.log(
    `Done. ${featureCount} stores → ${path.relative(REPO_ROOT, OUT_GEOJSON)} ` +
      `(${checkpoint.stats.apiCalls} API calls)`
  );
}

run().catch((err) => {
  console.error(err);
  process.exit(1);
});
