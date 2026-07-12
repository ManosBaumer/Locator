#!/usr/bin/env node
/**
 * Nationwide Mixue (蜜雪冰城) store scraper — per-city adaptive grid.
 *
 * findNear returns at most ~20 unique shops per point (page 2+ repeats). A nationwide
 * coarse grid wastes weeks subdividing empty wilderness; instead we crawl ~370 prefecture
 * cities (Amap centers) with a bounded adaptive grid each (same idea as McDonald's
 * deliveryinfo city crawl).
 *
 * API: POST https://mxsa.mxbc.net/api/v2/shopinfo/findNear  (distance max 20 km)
 *
 * Usage:
 *   node scripts/scrape-mixue.js                 # all mainland cities
 *   node scripts/scrape-mixue.js --test-beijing
 *   node scripts/scrape-mixue.js --test-guangzhou
 *   node scripts/scrape-mixue.js --resume
 *   node scripts/scrape-mixue.js --region east-south
 *   node scripts/scrape-mixue.js --merge-grid --resume  # nationwide grid + keep city stores
 *   node scripts/scrape-mixue.js --backup-city          # snapshot city crawl only
 *
 * Output:
 *   frontend/public/data/locations/mixue.geojson
 *   data/mixue-checkpoint.json (gitignored)
 */

const fs = require("fs");
const path = require("path");
const { findNearStores } = require("./lib/mixue-api");
const { loadCityCenters, filterCitiesByBbox } = require("./lib/mixue-cities");
const { gcj02ToWgs84 } = require("./lib/gcj02");

const REPO_ROOT = path.resolve(__dirname, "..");
const OUT_GEOJSON = path.join(
  REPO_ROOT,
  "frontend/public/data/locations/mixue.geojson"
);
const TEST_OUT_GEOJSON = path.join(REPO_ROOT, "data/mixue-test.geojson");
const CHECKPOINT_PATH = path.join(REPO_ROOT, "data/mixue-checkpoint.json");
const CITY_BACKUP_PATH = path.join(REPO_ROOT, "data/mixue-city-backup.json");
const CITY_GEOJSON_BACKUP_PATH = path.join(REPO_ROOT, "data/mixue-city.geojson.backup");
const TEST_CHECKPOINT_PATH = path.join(REPO_ROOT, "data/mixue-test-checkpoint.json");
const CHAINS_JSON = path.join(REPO_ROOT, "frontend/public/data/chains.json");
const MANIFEST_JSON = path.join(REPO_ROOT, "frontend/public/data/manifest.json");

const CHECKPOINT_VERSION = 7;

const DEFAULT_DELAY_MS = 30;
const DEFAULT_DISTANCE_KM = 20;
const DEFAULT_LIMIT = 100;
const DEFAULT_WORKERS = 16;

const API_RETRY_MAX_ATTEMPTS = 12;
const API_RETRY_BASE_MS = 2000;
const API_RETRY_MAX_MS = 60_000;
const API_ERROR_COOLDOWN_MS = 8000;
/** Mixue API codes / messages worth retrying (timeouts, overload). */
const TRANSIENT_API_CODES = new Set([5000, 5001, 502, 503, 504, 429]);

// Per-city bounded grid. API allows limit=100; with 20 km radius one call covers the
// whole cell unless saturated (100 results) — only then quad-subdivide (no empty/partial drill).
const CITY_INITIAL_STEP_DEGREES = 0.08;
const CITY_MIN_GRID_STEP_DEGREES = 0.004;
const CITY_BBOX_RADIUS_DEGREES = 0.18;
const MEGA_CITY_BBOX_RADIUS_DEGREES = 0.35;

// Legacy nationwide grid (only with --legacy-grid).
const LEGACY_INITIAL_GRID_STEP_DEGREES = 0.1;
const LEGACY_MIN_GRID_STEP_DEGREES = 0.004;
const LEGACY_EMPTY_CELL_SUBDIVIDE_MIN_STEP = 0.05;

const VISITED_PRECISION = 4;

const MEGA_CITIES = new Set([
  "广州市", "深圳市", "北京市", "上海市", "重庆市", "天津市",
  "东莞市", "佛山市", "武汉市", "成都市", "杭州市", "南京市",
  "西安市", "郑州市", "长沙市", "苏州市", "青岛市", "济南市",
  "合肥市", "福州市", "厦门市", "昆明市", "沈阳市", "哈尔滨市",
  "石家庄市", "南昌市", "南宁市", "贵阳市", "太原市", "兰州市",
]);

/** Crawl mega / tier-1 cities first on a fresh run (avoids alphabetical Anhui crawl). */
const CITY_CRAWL_ORDER = [
  "广州市", "深圳市", "东莞市", "佛山市", "上海市", "北京市", "重庆市", "成都市",
  "武汉市", "杭州市", "西安市", "苏州市", "郑州市", "南京市", "长沙市", "天津市",
  "青岛市", "济南市", "合肥市", "福州市", "厦门市", "昆明市", "沈阳市", "哈尔滨市",
  "石家庄市", "南昌市", "南宁市", "贵阳市", "太原市", "兰州市", "无锡市", "宁波市",
  "温州市", "泉州市", "南通市", "常州市", "徐州市", "烟台市", "大连市", "长春市",
  "惠州市", "中山市", "珠海市", "海口市", "三亚市", "兰州市", "乌鲁木齐市", "银川市",
  "西宁市", "呼和浩特市", "拉萨市",
];

const MAINLAND_BBOX = {
  minLat: 18.15,
  maxLat: 53.55,
  minLng: 73.66,
  maxLng: 134.77,
};

const REGION_FILTERS = {
  "east-south": { minLat: 20.0, maxLat: 42.0, minLng: 104.0, maxLng: 122.5 },
  northeast: { minLat: 38.5, maxLat: 53.2, minLng: 118.0, maxLng: 135.0 },
  southwest: { minLat: 21.0, maxLat: 34.0, minLng: 97.0, maxLng: 108.5 },
  northwest: { minLat: 35.0, maxLat: 49.5, minLng: 73.66, maxLng: 97.5 },
  "hainan-south": { minLat: 18.0, maxLat: 21.5, minLng: 108.5, maxLng: 111.5 },
  "north-central": { minLat: 37.0, maxLat: 45.0, minLng: 104.0, maxLng: 120.0 },
};

/** Areas skipped by overly broad HK/Macau grid exclusions — safe to re-crawl with --gapfill. */
const GAP_FILL_REGIONS = {
  "shenzhen-core": {
    name: "Shenzhen Futian / Luohu / Nanshan",
    bbox: { minLat: 22.42, maxLat: 22.58, minLng: 113.88, maxLng: 114.15 },
  },
  zhuhai: {
    name: "Zhuhai (old false Macau box)",
    bbox: { minLat: 22.15, maxLat: 22.45, minLng: 113.52, maxLng: 113.88 },
  },
};

const TEST_BEIJING = { centerLat: 39.9042, centerLng: 116.4074, name: "北京市" };
const TEST_GUANGZHOU = { centerLat: 23.1291, centerLng: 113.2644, name: "广州市" };

function parseArgs(argv) {
  const args = {
    resume: false,
    testBeijing: false,
    testGuangzhou: false,
    legacyGrid: false,
    mergeGrid: false,
    backupCityOnly: false,
    exportOnly: false,
    region: null,
    gapfill: null,
    delayMs: DEFAULT_DELAY_MS,
    distanceKm: DEFAULT_DISTANCE_KM,
    limit: DEFAULT_LIMIT,
    workers: DEFAULT_WORKERS,
    writePartial: true,
    maxPagesPerPoint: 1,
    verbose: false,
  };
  for (let i = 2; i < argv.length; i++) {
    const arg = argv[i];
    if (arg === "--resume") args.resume = true;
    else if (arg === "--legacy-grid") args.legacyGrid = true;
    else if (arg === "--merge-grid") args.mergeGrid = true;
    else if (arg === "--backup-city") args.backupCityOnly = true;
    else if (arg === "--export") args.exportOnly = true;
    else if (arg === "--test-beijing") {
      args.testBeijing = true;
      args.verbose = true;
      args.workers = 1;
    } else if (arg === "--test-guangzhou") {
      args.testGuangzhou = true;
      args.verbose = true;
      args.workers = 1;
    } else if (arg === "--verbose") args.verbose = true;
    else if (arg === "--no-partial") args.writePartial = false;
    else if (arg === "--region") args.region = argv[++i];
    else if (arg === "--gapfill") args.gapfill = argv[++i];
    else if (arg === "--delay") args.delayMs = Number(argv[++i]);
    else if (arg === "--distance") args.distanceKm = Number(argv[++i]);
    else if (arg === "--limit") args.limit = Number(argv[++i]);
    else if (arg === "--workers") args.workers = Number(argv[++i]);
    else if (arg === "--max-pages") args.maxPagesPerPoint = Number(argv[++i]);
    else if (arg === "--help" || arg === "-h") {
      console.log(`Usage: node scripts/scrape-mixue.js [options]

Per-city bounded adaptive grid (~370 prefecture cities; subdivides on any store hit).

Options:
  --test-beijing     Crawl Beijing city bbox only (verbose)
  --test-guangzhou   Crawl Guangzhou city bbox only (verbose)
  --resume           Continue from data/mixue-checkpoint.json
  --region NAME      Limit cities to a region (${Object.keys(REGION_FILTERS).join(", ")})
  --gapfill NAME     Re-crawl a missed bbox and merge (--resume required; ${Object.keys(GAP_FILL_REGIONS).join(", ")}, all)
  --legacy-grid      Old nationwide coarse grid (very slow — not recommended)
  --merge-grid       Nationwide grid merged into existing city stores (--resume required)
  --backup-city      Write data/mixue-city-backup.json from current checkpoint and exit
  --export           Re-write geojson + chains manifest from checkpoint (no crawl)
  --verbose          Log each API page / subdivision
  --workers N        Parallel grid workers (default ${DEFAULT_WORKERS})
  --delay MS         Delay between API calls per worker (default ${DEFAULT_DELAY_MS})
  --distance KM      Search radius per call, max 20 (default ${DEFAULT_DISTANCE_KM})
  --limit N          Page size, max 100 (default ${DEFAULT_LIMIT})
  --max-pages N      Max pages per point (default 1)
  --no-partial       Skip writing geojson until the end
`);
      process.exit(0);
    }
  }
  return args;
}

function isExcludedGridPoint(lat, lng) {
  // Match backend/app/ingestion/amap_regions.py — do NOT use a broad HK box that
  // swallows Shenzhen Futian/Nanshan (old bug: lat<=22.6 lng>=113.8).
  if (lng >= 113.5 && lng <= 113.6 && lat >= 22.08 && lat <= 22.22) return true;
  if (lat >= 22.1 && lat <= 22.45 && lng >= 113.83 && lng <= 114.45) return true;
  if (lat >= 21.9 && lat <= 25.4 && lng >= 119.3 && lng <= 122.1) return true;
  return false;
}

function cellInBbox(lat, lng, bbox) {
  return (
    lat >= bbox.minLat &&
    lat <= bbox.maxLat &&
    lng >= bbox.minLng &&
    lng <= bbox.maxLng
  );
}

function roundCoord(value) {
  return Math.round(value * 10 ** VISITED_PRECISION) / 10 ** VISITED_PRECISION;
}

function cellKey(cell) {
  return `${roundCoord(cell.lat)}|${roundCoord(cell.lng)}|${roundCoord(cell.step)}`;
}

function cellFromVisitedKey(key) {
  const [lat, lng, step] = key.split("|").map(Number);
  return { lat, lng, step };
}

function cityBboxRadius(cityName) {
  return MEGA_CITIES.has(cityName)
    ? MEGA_CITY_BBOX_RADIUS_DEGREES
    : CITY_BBOX_RADIUS_DEGREES;
}

function cityBbox(city) {
  const radius = cityBboxRadius(city.name);
  return {
    minLat: city.lat - radius,
    maxLat: city.lat + radius,
    minLng: city.lng - radius,
    maxLng: city.lng + radius,
  };
}

function iterGridInBbox(bbox, step) {
  const cells = [];
  for (let lat = bbox.minLat + step / 2; lat <= bbox.maxLat; lat += step) {
    for (let lng = bbox.minLng + step / 2; lng <= bbox.maxLng; lng += step) {
      if (isExcludedGridPoint(lat, lng)) continue;
      cells.push({ lat: roundCoord(lat), lng: roundCoord(lng), step });
    }
  }
  return cells;
}

function subdivideCell(lat, lng, step, clipBbox = null) {
  const quarter = step / 4;
  const halfStep = step / 2;
  const children = [];
  for (const dLat of [-quarter, quarter]) {
    for (const dLng of [-quarter, quarter]) {
      const childLat = roundCoord(lat + dLat);
      const childLng = roundCoord(lng + dLng);
      if (isExcludedGridPoint(childLat, childLng)) continue;
      if (clipBbox && !cellInBbox(childLat, childLng, clipBbox)) continue;
      children.push({ lat: childLat, lng: childLng, step: halfStep });
    }
  }
  return children;
}

function shouldSubdivide(shopCount, step, opts) {
  if (step <= opts.minStep) return false;
  if (opts.saturatedOnly) {
    return shopCount >= opts.limit;
  }
  if (shopCount > 0) return true;
  return step > opts.emptyMinStep;
}

function distanceKmForStep(stepDegrees, maxKm = DEFAULT_DISTANCE_KM) {
  // Match search radius to cell size (~250 km per degree). Using 20 km at every depth
  // returns the same 100 city-wide shops and subdivision never converges.
  const scaled = Math.max(1, Math.min(maxKm, stepDegrees * 250));
  return Math.round(scaled * 10) / 10;
}

function cityCrawlRank(cityName) {
  const idx = CITY_CRAWL_ORDER.indexOf(cityName);
  if (idx >= 0) return idx;
  if (MEGA_CITIES.has(cityName)) return CITY_CRAWL_ORDER.length + 1;
  return CITY_CRAWL_ORDER.length + 100;
}

/** Mini-program test / internal shops — not public retail locations. */
const TEST_SHOP_NAME_RE =
  /测试|请勿下单|不要点餐|勿动|内部门店|数字门店|培训门店|培训中心|客户请勿下单/i;
const TEST_ADDRESS_RE = /测试区域|测试门店|罗布泊|^是是是$|^sga$/i;
const TEST_REGION_NAMES = new Set(["无人区", "台湾测试区域"]);
const TEST_SHOP_CODES = new Set([
  "888888",
  "11223344",
  "123456",
  "400001",
  "400002",
  "400003",
  "400004",
  "400005",
  "400006",
  "400008",
  "1000000",
  "1000001",
  "1000002",
  "1000004",
  "100000001",
  "100000002",
]);

function isTestOrInternalShop(shop) {
  if (!shop) return true;
  const name = String(shop.shopName || "");
  const address = String(shop.shopAddress || "");
  const regionName = String(shop.regionName || "");
  const regionCode = String(shop.regionCode || "");
  const shopCode = String(shop.shopCode || "");

  if (TEST_SHOP_CODES.has(shopCode)) return true;
  if (regionCode === "999999" || regionCode.startsWith("83")) return true;
  if (TEST_REGION_NAMES.has(regionName)) return true;
  if (TEST_SHOP_NAME_RE.test(name)) return true;
  if (TEST_ADDRESS_RE.test(address)) return true;
  if (/培训/.test(name) && /请勿下单|内部门店|测试/.test(name)) return true;
  return false;
}

function isMainlandShop(shop) {
  if (!shop || shop.isOversea === 1) return false;
  const code = String(shop.regionCode || "");
  if (code.startsWith("71") || code.startsWith("81") || code.startsWith("82")) {
    return false;
  }
  const lat = Number(shop.latitude);
  const lng = Number(shop.longitude);
  if (!Number.isFinite(lat) || !Number.isFinite(lng)) return false;
  if (lat < 17.5 || lat > 54.5 || lng < 72 || lng > 136) return false;
  return true;
}

function isRetailShop(shop) {
  return isMainlandShop(shop) && !isTestOrInternalShop(shop);
}

function shopNumericId(shopId) {
  let hash = 0;
  for (const ch of String(shopId)) {
    hash = (hash * 31 + ch.charCodeAt(0)) >>> 0;
  }
  return hash || 1;
}

function shopToFeature(shop) {
  const id = shopNumericId(shop.shopId);
  const gcjLng = Number(shop.longitude);
  const gcjLat = Number(shop.latitude);
  const [lng, lat] = gcj02ToWgs84(gcjLng, gcjLat);
  return {
    type: "Feature",
    id,
    geometry: {
      type: "Point",
      coordinates: [lng, lat],
    },
    properties: {
      id,
      name: shop.shopName,
      chain_slug: "mixue",
      category_slug: "tea-shop",
      address: shop.shopAddress || null,
      city: shop.regionName || null,
      shop_id: shop.shopId,
      shop_code: shop.shopCode || null,
    },
  };
}

function storesToGeojson(storesById) {
  const features = Object.values(storesById)
    .filter(isRetailShop)
    .map(shopToFeature)
    .sort((a, b) => a.id - b.id);
  return { type: "FeatureCollection", features };
}

function emptyCheckpoint(mode = "city") {
  return {
    version: CHECKPOINT_VERSION,
    mode,
    stores: {},
    completedCityKeys: [],
    pendingCities: [],
    activeCity: null,
    visited: [],
    queue: [],
    stats: {
      apiCalls: 0,
      pages: 0,
      cellsProcessed: 0,
      subdivisions: 0,
      citiesCompleted: 0,
    },
  };
}

function countStoresNearCity(stores, city) {
  const radius = cityBboxRadius(city.name);
  let count = 0;
  for (const shop of Object.values(stores)) {
    const lat = Number(shop.latitude);
    const lng = Number(shop.longitude);
    if (
      Math.abs(lat - city.lat) <= radius &&
      Math.abs(lng - city.lng) <= radius
    ) {
      count += 1;
    }
  }
  return count;
}

function prioritizeCities(cities, stores) {
  return cities
    .map((city) => ({
      ...city,
      seedCount: countStoresNearCity(stores, city),
    }))
    .sort(
      (a, b) =>
        cityCrawlRank(a.name) - cityCrawlRank(b.name) ||
        b.seedCount - a.seedCount ||
        a.key.localeCompare(b.key, "zh")
    );
}

async function buildCityQueue(args, stores) {
  if (args.testBeijing) {
    return [
      {
        key: "test|北京市",
        province: "北京",
        name: TEST_BEIJING.name,
        lat: TEST_BEIJING.centerLat,
        lng: TEST_BEIJING.centerLng,
      },
    ];
  }
  if (args.testGuangzhou) {
    return [
      {
        key: "test|广州市",
        province: "广东",
        name: TEST_GUANGZHOU.name,
        lat: TEST_GUANGZHOU.centerLat,
        lng: TEST_GUANGZHOU.centerLng,
      },
    ];
  }

  const allCities = await loadCityCenters();
  const regionBbox = args.region ? REGION_FILTERS[args.region] : null;
  const filtered = filterCitiesByBbox(allCities, regionBbox);
  if (filtered.length === 0) {
    throw new Error(`No cities in region: ${args.region}`);
  }
  return prioritizeCities(filtered, stores);
}

function enrichCities(cities) {
  const cachePath = path.join(REPO_ROOT, "data/mixue-city-centers.json");
  if (!fs.existsSync(cachePath)) {
    return cities.filter((c) => c.lat != null && c.lng != null);
  }
  const byKey = new Map(
    JSON.parse(fs.readFileSync(cachePath, "utf8")).map((c) => [c.key, c])
  );
  return cities
    .map((c) => {
      if (c.lat != null && c.lng != null) return c;
      return byKey.get(c.key) || null;
    })
    .filter(Boolean);
}

function migrateCheckpoint(raw, args) {
  const storeCount = Object.keys(raw.stores || {}).length;
  const stats = {
    apiCalls: raw.stats?.apiCalls ?? 0,
    pages: raw.stats?.pages ?? 0,
    cellsProcessed: raw.stats?.cellsProcessed ?? 0,
    subdivisions: raw.stats?.subdivisions ?? 0,
    citiesCompleted: raw.stats?.citiesCompleted ?? 0,
  };

  if (args.legacyGrid) {
    if (raw.version === 3) return raw;
    console.log(
      `Checkpoint v${raw.version ?? 1} → legacy v3: keeping ${storeCount} stores, rebuilding nationwide queue`
    );
    return {
      version: 3,
      mode: "legacy",
      visited: [],
      queue: [],
      stores: raw.stores || {},
      stats: { ...stats, cellsProcessed: 0, subdivisions: 0 },
    };
  }

  if (args.mergeGrid) {
    if (raw.version === CHECKPOINT_VERSION && raw.mode === "merge-grid") {
      return raw;
    }
    backupCityStores(raw);
    const cityStoreCount = Object.keys(raw.stores || {}).length;
    console.log(
      `Checkpoint → merge-grid: keeping ${cityStoreCount} city stores, starting nationwide grid pass`
    );
    return {
      version: CHECKPOINT_VERSION,
      mode: "merge-grid",
      stores: { ...(raw.stores || {}) },
      cityStoreCount,
      cityBackupPath: path.relative(REPO_ROOT, CITY_BACKUP_PATH),
      visited: [],
      queue: [],
      completedCityKeys: raw.completedCityKeys || [],
      stats: {
        apiCalls: raw.stats?.apiCalls ?? 0,
        pages: raw.stats?.pages ?? 0,
        cellsProcessed: 0,
        subdivisions: 0,
        citiesCompleted: raw.stats?.citiesCompleted ?? 0,
        gridCellsProcessed: 0,
        gridSubdivisions: 0,
      },
    };
  }

  if (raw.mode === "merge-grid") {
    return raw;
  }

  if (raw.mode === "city" && raw.version >= 4) {
    return raw;
  }

  if (raw.version >= 4 && raw.mode === "city") {
    const pending = [...(raw.pendingCities || [])];
    if (raw.activeCity) {
      pending.unshift({
        key: raw.activeCity.key,
        province: raw.activeCity.province,
        name: raw.activeCity.name,
        lat: raw.activeCity.lat,
        lng: raw.activeCity.lng,
      });
    }
    const deduped = [];
    const seen = new Set();
    for (const city of pending) {
      if (!city?.key || seen.has(city.key)) continue;
      seen.add(city.key);
      deduped.push(city);
    }
    console.log(
      `Checkpoint v${raw.version} → v${CHECKPOINT_VERSION} (scaled distance + limit 100): ` +
        `keeping ${storeCount} stores, re-crawling all cities with faster grid, re-sorting queue`
    );
    return {
      ...raw,
      version: CHECKPOINT_VERSION,
      completedCityKeys: [],
      stats: { ...stats, citiesCompleted: 0 },
      pendingCities: prioritizeCities(enrichCities(deduped), raw.stores || {}),
      activeCity: null,
    };
  }

  console.log(
    `Checkpoint v${raw.version ?? 1} → v${CHECKPOINT_VERSION} (per-city crawl): keeping ${storeCount} stores, ` +
      `discarding ${(raw.queue || []).length} nationwide queue cells`
  );
  return {
    version: CHECKPOINT_VERSION,
    mode: "city",
    stores: raw.stores || {},
    completedCityKeys: [],
    pendingCities: [],
    activeCity: null,
    visited: [],
    queue: [],
    stats: { ...stats, cellsProcessed: 0, subdivisions: 0, citiesCompleted: 0 },
  };
}

function loadCheckpoint(checkpointPath, args) {
  if (!fs.existsSync(checkpointPath)) {
    return emptyCheckpoint(args.legacyGrid ? "legacy" : "city");
  }
  const raw = JSON.parse(fs.readFileSync(checkpointPath, "utf8"));
  if (args.mergeGrid || args.legacyGrid) {
    return migrateCheckpoint(raw, args);
  }
  if (raw.mode === "merge-grid") {
    return raw;
  }
  return migrateCheckpoint(raw, args);
}

function saveCheckpoint(checkpoint, checkpointPath = CHECKPOINT_PATH) {
  fs.mkdirSync(path.dirname(checkpointPath), { recursive: true });
  fs.writeFileSync(checkpointPath, JSON.stringify(checkpoint, null, 0));
}

function backupCityStores(checkpoint, { force = false } = {}) {
  const storeCount = Object.keys(checkpoint.stores || {}).length;
  if (storeCount === 0) {
    throw new Error("Cannot backup: checkpoint has no stores");
  }
  if (fs.existsSync(CITY_BACKUP_PATH) && !force) {
    const existing = JSON.parse(fs.readFileSync(CITY_BACKUP_PATH, "utf8"));
    console.log(
      `City backup already exists (${existing.storeCount} stores) → ${path.relative(REPO_ROOT, CITY_BACKUP_PATH)}`
    );
    return existing;
  }

  const backup = {
    version: 1,
    backedUpAt: new Date().toISOString(),
    storeCount,
    citiesCompleted: checkpoint.stats?.citiesCompleted ?? 0,
    stores: checkpoint.stores,
  };
  fs.mkdirSync(path.dirname(CITY_BACKUP_PATH), { recursive: true });
  fs.writeFileSync(CITY_BACKUP_PATH, JSON.stringify(backup, null, 0));

  if (fs.existsSync(OUT_GEOJSON)) {
    fs.copyFileSync(OUT_GEOJSON, CITY_GEOJSON_BACKUP_PATH);
  } else {
    writeGeojson(checkpoint.stores, CITY_GEOJSON_BACKUP_PATH);
  }

  console.log(
    `Backed up ${storeCount} city stores → ${path.relative(REPO_ROOT, CITY_BACKUP_PATH)}` +
      ` and ${path.relative(REPO_ROOT, CITY_GEOJSON_BACKUP_PATH)}`
  );
  return backup;
}

function loadCityBackupStores() {
  if (!fs.existsSync(CITY_BACKUP_PATH)) {
    return null;
  }
  const backup = JSON.parse(fs.readFileSync(CITY_BACKUP_PATH, "utf8"));
  return backup.stores || null;
}

function mergeStoresIntoCheckpoint(checkpoint, storesById) {
  if (!storesById) return 0;
  let added = 0;
  for (const [shopId, shop] of Object.entries(storesById)) {
    if (!checkpoint.stores[shopId]) added += 1;
    checkpoint.stores[shopId] = shop;
  }
  return added;
}

function writeGeojson(storesById, outPath = OUT_GEOJSON) {
  fs.mkdirSync(path.dirname(outPath), { recursive: true });
  const payload = storesToGeojson(storesById);
  fs.writeFileSync(outPath, JSON.stringify(payload));
  return payload.features.length;
}

function updateManifestAndChains(featureCount) {
  let chains = [];
  if (fs.existsSync(CHAINS_JSON)) {
    chains = JSON.parse(fs.readFileSync(CHAINS_JSON, "utf8"));
  }
  const existing = chains.find((c) => c.slug === "mixue");
  if (existing) {
    existing.location_count = featureCount;
    existing.name = "蜜雪冰城 / Mixue";
    existing.category_slug = "tea-shop";
  } else {
    const maxId = chains.reduce((m, c) => Math.max(m, c.id || 0), 0);
    chains.push({
      id: maxId + 1,
      name: "蜜雪冰城 / Mixue",
      slug: "mixue",
      category_slug: "tea-shop",
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

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function isTransientMixuePayload(payload) {
  if (!payload || payload.code === 0) return false;
  if (TRANSIENT_API_CODES.has(payload.code)) return true;
  const msg = String(payload.msg || "").toLowerCase();
  return (
    msg.includes("timeout") ||
    msg.includes("timed out") ||
    msg.includes("too many") ||
    msg.includes("频繁") ||
    msg.includes("busy") ||
    msg.includes("overload")
  );
}

function isTransientFetchError(err) {
  if (!err) return false;
  const msg = String(err.message || err).toLowerCase();
  return (
    err.name === "AbortError" ||
    err.name === "FetchError" ||
    msg.includes("fetch failed") ||
    msg.includes("network") ||
    msg.includes("timeout") ||
    msg.includes("econnreset") ||
    msg.includes("econnrefused") ||
    msg.includes("socket hang up") ||
    err.transient === true
  );
}

function retryDelayMs(attempt) {
  const base = Math.min(API_RETRY_MAX_MS, API_RETRY_BASE_MS * 2 ** (attempt - 1));
  return Math.round(base * (0.85 + Math.random() * 0.3));
}

async function findNearStoresWithRetry(params, opts = {}) {
  const { checkpoint, verbose, context = "" } = opts;
  let lastError = null;

  for (let attempt = 1; attempt <= API_RETRY_MAX_ATTEMPTS; attempt += 1) {
    try {
      const payload = await findNearStores(params);
      if (payload.code === 0) {
        return payload;
      }
      if (!isTransientMixuePayload(payload)) {
        const err = new Error(
          `Mixue API error${context}: code=${payload.code} msg=${payload.msg || ""}`
        );
        err.transient = false;
        throw err;
      }
      lastError = new Error(
        `Mixue API error${context}: code=${payload.code} msg=${payload.msg || ""}`
      );
      lastError.transient = true;
    } catch (err) {
      if (err.transient === false || (!isTransientFetchError(err) && err.transient !== true)) {
        throw err;
      }
      lastError = err;
      lastError.transient = true;
    }

    if (attempt >= API_RETRY_MAX_ATTEMPTS) break;

    if (checkpoint?.stats) {
      checkpoint.stats.apiRetries = (checkpoint.stats.apiRetries || 0) + 1;
    }
    const waitMs = retryDelayMs(attempt);
    console.warn(
      `\n  Mixue API busy${context} (attempt ${attempt}/${API_RETRY_MAX_ATTEMPTS}) — waiting ${Math.round(waitMs / 1000)}s...`
    );
    await sleep(waitMs);
  }

  throw lastError || new Error(`Mixue API failed${context} after ${API_RETRY_MAX_ATTEMPTS} attempts`);
}

function isRetryableCellError(err) {
  if (err?.transient === true || isTransientFetchError(err)) return true;
  return /code=(5000|5001|502|503|504|429)/.test(String(err?.message || ""));
}

async function fetchAllPagesAtPoint(lat, lng, opts) {
  const shops = [];
  const seenAtPoint = new Set();
  let page = 1;
  while (true) {
    if (opts.verbose) {
      console.log(`    API page ${page} @ ${lat},${lng} step=${opts.cellStep} ...`);
    }
    const payload = await findNearStoresWithRetry(
      {
        latitude: lat,
        longitude: lng,
        page,
        limit: opts.limit,
        distance: opts.scaledDistance
          ? distanceKmForStep(opts.cellStep, opts.distanceKm)
          : opts.distanceKm,
      },
      {
        checkpoint: opts.checkpoint,
        verbose: opts.verbose,
        context: ` at (${lat},${lng}) page ${page}`,
      }
    );
    opts.checkpoint.stats.apiCalls += 1;
    opts.checkpoint.stats.pages += 1;

    const batch = (payload.data || []).filter(isRetailShop);
    let newCount = 0;
    for (const shop of batch) {
      if (seenAtPoint.has(shop.shopId)) continue;
      seenAtPoint.add(shop.shopId);
      shops.push(shop);
      newCount += 1;
    }
    if (opts.verbose) {
      console.log(
        `    page ${page}: ${batch.length} returned, +${newCount} new (${shops.length} at point)`
      );
    }
    if (batch.length < opts.limit || newCount === 0) break;
    if (page >= opts.maxPagesPerPoint) break;
    page += 1;
    await sleep(opts.delayMs);
  }
  return shops;
}

class WorkQueue {
  constructor(items = []) {
    this.items = items.slice();
  }

  pushMany(cells) {
    for (const cell of cells) {
      this.items.push(cell);
    }
  }

  shift() {
    return this.items.shift();
  }

  get size() {
    return this.items.length;
  }
}

function seedCityGrid(city) {
  const bbox = cityBbox(city);
  return iterGridInBbox(bbox, CITY_INITIAL_STEP_DEGREES);
}

function seedLegacyGrid(args) {
  const bbox = args.region ? REGION_FILTERS[args.region] : MAINLAND_BBOX;
  if (!bbox) throw new Error(`Unknown region: ${args.region}`);
  return iterGridInBbox(bbox, LEGACY_INITIAL_GRID_STEP_DEGREES);
}

function gridOpts(kind, args) {
  if (kind === "legacy") {
    return {
      minStep: LEGACY_MIN_GRID_STEP_DEGREES,
      emptyMinStep: LEGACY_EMPTY_CELL_SUBDIVIDE_MIN_STEP,
      saturatedOnly: false,
      limit: args.limit,
    };
  }
  return {
    minStep: CITY_MIN_GRID_STEP_DEGREES,
    saturatedOnly: true,
    limit: args.limit,
  };
}

async function crawlAdaptiveGrid({
  args,
  checkpoint,
  checkpointPath,
  visited,
  queue,
  gridOptions,
  clipBbox = null,
  scaledDistance = false,
  onProgress,
}) {
  let lastWrite = Date.now();

  async function processCell(cell) {
    const key = cellKey(cell);
    if (visited.has(key)) return null;
    visited.add(key);

    const shops = await fetchAllPagesAtPoint(cell.lat, cell.lng, {
      ...args,
      cellStep: cell.step,
      checkpoint,
      scaledDistance,
    });

    let newGlobal = 0;
    for (const shop of shops) {
      if (!checkpoint.stores[shop.shopId]) newGlobal += 1;
      checkpoint.stores[shop.shopId] = shop;
    }

    checkpoint.stats.cellsProcessed += 1;

    let children = [];
    if (shouldSubdivide(shops.length, cell.step, gridOptions)) {
      children = subdivideCell(cell.lat, cell.lng, cell.step, clipBbox);
      checkpoint.stats.subdivisions += 1;
      if (args.verbose) {
        console.log(
          `  subdivide ${cell.lat},${cell.lng} step=${cell.step} (${shops.length} shops) → +${children.length} children`
        );
      }
    } else if (args.verbose) {
      console.log(
        `  cell done ${cell.lat},${cell.lng} step=${cell.step}: ${shops.length} shops (+${newGlobal} new)`
      );
    }

    return children;
  }

  async function worker() {
    while (true) {
      const cell = queue.shift();
      if (!cell) return;

      if (visited.has(cellKey(cell))) continue;

      try {
        const children = await processCell(cell);
        if (children && children.length > 0) {
          queue.pushMany(children);
        }
      } catch (err) {
        const key = cellKey(cell);
        visited.delete(key);
        checkpoint.stats.apiErrors = (checkpoint.stats.apiErrors || 0) + 1;
        if (isRetryableCellError(err)) {
          queue.push(cell);
          console.warn(
            `\n  Cell failed @ ${cell.lat},${cell.lng}: ${err.message} — re-queued, cooling down ${Math.round(API_ERROR_COOLDOWN_MS / 1000)}s`
          );
          checkpoint.visited = Array.from(visited);
          checkpoint.queue = queue.items;
          saveCheckpoint(checkpoint, checkpointPath);
          await sleep(API_ERROR_COOLDOWN_MS);
        } else {
          visited.add(key);
          console.error(
            `\n  Cell skipped (non-retryable) @ ${cell.lat},${cell.lng}: ${err.message}`
          );
        }
        continue;
      }

      await sleep(args.delayMs);

      if (onProgress) {
        onProgress();
      }

      if (args.writePartial && Date.now() - lastWrite > 60_000) {
        const count = writeGeojson(checkpoint.stores, args.outGeojson);
        console.log(`\n  checkpoint write: ${count} features`);
        lastWrite = Date.now();
      }
    }
  }

  const workers = Math.max(1, args.workers);
  await Promise.all(Array.from({ length: workers }, () => worker()));
}

async function runCityMode(args, checkpoint, checkpointPath) {
  if (!checkpoint.pendingCities.length && !checkpoint.activeCity) {
    const cities = await buildCityQueue(args, checkpoint.stores);
    const completed = new Set(checkpoint.completedCityKeys || []);
    checkpoint.pendingCities = cities.filter((c) => !completed.has(c.key));
    console.log(
      `City queue: ${checkpoint.pendingCities.length} cities` +
        (checkpoint.pendingCities[0]
          ? ` (first: ${checkpoint.pendingCities[0].name}, ${checkpoint.pendingCities[0].seedCount ?? 0} seed stores)`
          : "")
    );
  }

  let lastProgressLine = 0;

  while (checkpoint.activeCity || checkpoint.pendingCities.length > 0) {
    if (!checkpoint.activeCity) {
      const city = checkpoint.pendingCities.shift();
      if (!city?.lat) {
        throw new Error(`City missing coordinates: ${city?.name || city?.key}`);
      }
      const seeds = seedCityGrid(city);
      checkpoint.activeCity = {
        key: city.key,
        name: city.name,
        province: city.province,
        lat: city.lat,
        lng: city.lng,
        visited: [],
        queue: seeds,
      };
      console.log(
        `\n→ ${city.name} (${city.province}) — seed ${seeds.length} cells, radius ${cityBboxRadius(city.name)}°`
      );
    }

    const active = checkpoint.activeCity;
    const cityForBbox = {
      name: active.name,
      lat: active.lat,
      lng: active.lng,
    };
    const visited = new Set(active.visited);
    const queue = new WorkQueue(active.queue);
    const storeCountBefore = Object.keys(checkpoint.stores).length;

    await crawlAdaptiveGrid({
      args: { ...args, outGeojson: args.outGeojson },
      checkpoint,
      checkpointPath,
      visited,
      queue,
      gridOptions: gridOpts("city", args),
      clipBbox: cityBbox(cityForBbox),
      scaledDistance: true,
      onProgress() {
        if (checkpoint.stats.cellsProcessed - lastProgressLine >= 10) {
          lastProgressLine = checkpoint.stats.cellsProcessed;
          const storeCount = Object.keys(checkpoint.stores).length;
          process.stdout.write(
            `\r  ${active.name}: queue=${queue.size} stores=${storeCount} (+${storeCount - storeCountBefore} this city) api=${checkpoint.stats.apiCalls}   `
          );
        }
        if (checkpoint.stats.cellsProcessed % 25 === 0) {
          active.visited = Array.from(visited);
          active.queue = queue.items;
          saveCheckpoint(checkpoint, checkpointPath);
        }
      },
    });

    const added = Object.keys(checkpoint.stores).length - storeCountBefore;
    checkpoint.completedCityKeys.push(active.key);
    checkpoint.stats.citiesCompleted += 1;
    checkpoint.activeCity = null;
    saveCheckpoint(checkpoint, checkpointPath);
    console.log(
      `\n  ✓ ${active.name} done (+${added} stores, total ${Object.keys(checkpoint.stores).length}, ${checkpoint.pendingCities.length} cities left)`
    );
  }
}

async function runGapFillMode(args, checkpoint, checkpointPath, regionKey) {
  const entries =
    regionKey === "all"
      ? Object.entries(GAP_FILL_REGIONS)
      : [[regionKey, GAP_FILL_REGIONS[regionKey]]];

  if (!entries[0]?.[1]) {
    throw new Error(
      `Unknown gap-fill region: ${regionKey} (use ${Object.keys(GAP_FILL_REGIONS).join(", ")}, or all)`
    );
  }

  for (const [, region] of entries) {
    const storeCountBefore = Object.keys(checkpoint.stores).length;
    const visited = new Set();
    const queue = new WorkQueue(iterGridInBbox(region.bbox, CITY_INITIAL_STEP_DEGREES));
    console.log(
      `\nGap-fill: ${region.name} — ${queue.size} seed cells (merging into ${storeCountBefore} existing stores)`
    );

    let lastProgressLine = checkpoint.stats.cellsProcessed;
    await crawlAdaptiveGrid({
      args: { ...args, outGeojson: args.outGeojson },
      checkpoint,
      checkpointPath,
      visited,
      queue,
      gridOptions: gridOpts("city", args),
      clipBbox: region.bbox,
      scaledDistance: true,
      onProgress() {
        if (checkpoint.stats.cellsProcessed - lastProgressLine >= 10) {
          lastProgressLine = checkpoint.stats.cellsProcessed;
          const storeCount = Object.keys(checkpoint.stores).length;
          process.stdout.write(
            `\r  ${region.name}: queue=${queue.size} stores=${storeCount} (+${storeCount - storeCountBefore}) api=${checkpoint.stats.apiCalls}   `
          );
        }
      },
    });

    const added = Object.keys(checkpoint.stores).length - storeCountBefore;
    saveCheckpoint(checkpoint, checkpointPath);
    console.log(
      `\n  ✓ ${region.name}: +${added} new stores (total ${Object.keys(checkpoint.stores).length})`
    );
  }
}

async function runMergeGridMode(args, checkpoint, checkpointPath) {
  const backupStores = loadCityBackupStores();
  if (backupStores) {
    mergeStoresIntoCheckpoint(checkpoint, backupStores);
  }
  const cityBaseline =
    checkpoint.cityStoreCount ?? (backupStores ? Object.keys(backupStores).length : 0);

  const visited = new Set(checkpoint.visited || []);
  const queue = new WorkQueue(checkpoint.queue || []);
  const mainlandBbox = args.region ? REGION_FILTERS[args.region] : MAINLAND_BBOX;

  if (queue.size === 0) {
    const seeds = seedLegacyGrid(args);
    queue.pushMany(seeds);
    console.log(
      `Seeded ${seeds.length} coarse mainland cells (merge-grid adds to ${Object.keys(checkpoint.stores).length} existing stores)`
    );
  }

  console.log(
    `Merge-grid pass: stores=${Object.keys(checkpoint.stores).length} (city baseline ${cityBaseline}), queue=${queue.size}`
  );

  let lastProgress = checkpoint.stats.gridCellsProcessed || 0;
  const storeCountAtStart = Object.keys(checkpoint.stores).length;

  await crawlAdaptiveGrid({
    args: { ...args, outGeojson: args.outGeojson },
    checkpoint,
    checkpointPath,
    visited,
    queue,
    gridOptions: gridOpts("merge", args),
    clipBbox: mainlandBbox,
    scaledDistance: true,
    onProgress() {
      checkpoint.stats.gridCellsProcessed = checkpoint.stats.cellsProcessed;
      checkpoint.stats.gridSubdivisions = checkpoint.stats.subdivisions;
      if (checkpoint.stats.gridCellsProcessed % 25 === 0) {
        checkpoint.visited = Array.from(visited);
        checkpoint.queue = queue.items;
        saveCheckpoint(checkpoint, checkpointPath);
      }
      if (!args.verbose && checkpoint.stats.gridCellsProcessed - lastProgress >= 10) {
        lastProgress = checkpoint.stats.gridCellsProcessed;
        const storeCount = Object.keys(checkpoint.stores).length;
        process.stdout.write(
          `\r  grid: queue=${queue.size} stores=${storeCount} (+${storeCount - storeCountAtStart} beyond city) api=${checkpoint.stats.apiCalls}   `
        );
      }
    },
  });

  checkpoint.visited = Array.from(visited);
  checkpoint.queue = [];
  const added = Object.keys(checkpoint.stores).length - storeCountAtStart;
  console.log(
    `\n  Grid pass added ${added} new stores (${Object.keys(checkpoint.stores).length} total, ${cityBaseline} from city crawl)`
  );
}

async function runLegacyMode(args, checkpoint, checkpointPath) {
  const visited = new Set(checkpoint.visited || []);
  const queue = new WorkQueue(checkpoint.queue || []);

  if (queue.size === 0) {
    const seeds = seedLegacyGrid(args);
    queue.pushMany(seeds);
    console.log(`Seeded ${seeds.length} coarse nationwide grid cells (legacy mode)`);
  }

  console.log(
    `Mixue legacy scrape: queue=${queue.size} visited=${visited.size} stores=${Object.keys(checkpoint.stores).length}`
  );

  let lastProgress = 0;

  await crawlAdaptiveGrid({
    args: { ...args, outGeojson: args.outGeojson },
    checkpoint,
    checkpointPath,
    visited,
    queue,
    gridOptions: gridOpts("legacy", args),
    scaledDistance: false,
    onProgress() {
      if (checkpoint.stats.cellsProcessed % 25 === 0) {
        checkpoint.visited = Array.from(visited);
        checkpoint.queue = queue.items;
        saveCheckpoint(checkpoint, checkpointPath);
      }
      if (!args.verbose && checkpoint.stats.cellsProcessed - lastProgress >= 10) {
        lastProgress = checkpoint.stats.cellsProcessed;
        const storeCount = Object.keys(checkpoint.stores).length;
        process.stdout.write(
          `\r  cells=${checkpoint.stats.cellsProcessed} queue=${queue.size} stores=${storeCount} api=${checkpoint.stats.apiCalls} subdiv=${checkpoint.stats.subdivisions}   `
        );
      }
    },
  });

  checkpoint.visited = Array.from(visited);
  checkpoint.queue = [];
}

async function run() {
  const args = parseArgs(process.argv);
  const isTest = args.testBeijing || args.testGuangzhou;
  args.outGeojson = isTest ? TEST_OUT_GEOJSON : OUT_GEOJSON;
  const checkpointPath = isTest ? TEST_CHECKPOINT_PATH : CHECKPOINT_PATH;

  if (args.backupCityOnly) {
    if (isTest) {
      throw new Error("--backup-city cannot be used with test modes");
    }
    const cp = loadCheckpoint(checkpointPath, args);
    backupCityStores(cp, { force: true });
    return;
  }

  if (args.exportOnly) {
    if (isTest) {
      throw new Error("--export cannot be used with test modes");
    }
    const checkpoint = loadCheckpoint(checkpointPath, args);
    const rawCount = Object.keys(checkpoint.stores).length;
    const featureCount = writeGeojson(checkpoint.stores, args.outGeojson);
    updateManifestAndChains(featureCount);
    const filtered = rawCount - featureCount;
    console.log(
      `Exported ${featureCount} retail stores → ${path.relative(REPO_ROOT, args.outGeojson)}` +
        (filtered > 0 ? ` (filtered ${filtered} test/internal)` : "")
    );
    return;
  }

  if (args.mergeGrid) {
    if (isTest) {
      throw new Error("--merge-grid cannot be used with test modes");
    }
    if (!args.resume) {
      throw new Error("--merge-grid requires --resume (merges into existing city checkpoint)");
    }
    const checkpoint = loadCheckpoint(checkpointPath, args);
    console.log(
      `Mixue merge-grid: ${Object.keys(checkpoint.stores).length} stores, city backup at ${checkpoint.cityBackupPath || "data/mixue-city-backup.json"}`
    );
    await runMergeGridMode(args, checkpoint, checkpointPath);
    saveCheckpoint(checkpoint, checkpointPath);
    const featureCount = writeGeojson(checkpoint.stores, args.outGeojson);
    updateManifestAndChains(featureCount);
    console.log(`Done. ${featureCount} stores → ${path.relative(REPO_ROOT, args.outGeojson)}`);
    return;
  }

  const checkpoint =
    args.resume && !isTest
      ? loadCheckpoint(checkpointPath, args)
      : emptyCheckpoint(args.legacyGrid ? "legacy" : "city");

  if (args.gapfill) {
    if (isTest) {
      throw new Error("--gapfill cannot be used with test modes");
    }
    if (!args.resume) {
      throw new Error("--gapfill requires --resume (merges into existing checkpoint; never wipes stores)");
    }
    console.log(`Mixue gap-fill: stores=${Object.keys(checkpoint.stores).length}`);
    await runGapFillMode(args, checkpoint, checkpointPath, args.gapfill);
    saveCheckpoint(checkpoint, checkpointPath);
    const featureCount = writeGeojson(checkpoint.stores, args.outGeojson);
    updateManifestAndChains(featureCount);
    console.log(`Done. ${featureCount} stores → ${path.relative(REPO_ROOT, args.outGeojson)}`);
    return;
  }

  console.log(
    `Mixue scrape (${checkpoint.mode}): stores=${Object.keys(checkpoint.stores).length}` +
      (checkpoint.mode === "city"
        ? ` cities=${checkpoint.stats.citiesCompleted}/${checkpoint.stats.citiesCompleted + checkpoint.pendingCities.length + (checkpoint.activeCity ? 1 : 0)}`
        : "")
  );

  if (args.testBeijing || args.testGuangzhou) {
    checkpoint.pendingCities = await buildCityQueue(args, checkpoint.stores);
    checkpoint.completedCityKeys = [];
    checkpoint.activeCity = null;
    console.log(`Test output: ${path.relative(REPO_ROOT, args.outGeojson)}`);
  }

  if (checkpoint.mode === "legacy" || args.legacyGrid) {
    await runLegacyMode(args, checkpoint, checkpointPath);
  } else {
    await runCityMode(args, checkpoint, checkpointPath);
  }

  saveCheckpoint(checkpoint, checkpointPath);
  const featureCount = writeGeojson(checkpoint.stores, args.outGeojson);
  if (!isTest) {
    updateManifestAndChains(featureCount);
  }
  console.log(
    `Done. ${featureCount} stores → ${path.relative(REPO_ROOT, args.outGeojson)}`
  );
  console.log(
    `Cities: ${checkpoint.stats.citiesCompleted}, cells: ${checkpoint.stats.cellsProcessed}, API calls: ${checkpoint.stats.apiCalls}`
  );
}

run().catch((err) => {
  console.error(err);
  process.exit(1);
});
