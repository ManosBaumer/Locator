#!/usr/bin/env node
/**
 * Nationwide Mixue (蜜雪冰城) store scraper — adaptive grid.
 *
 * findNear returns at most ~20 unique shops per point (page 2+ repeats). A fixed
 * coarse grid leaves holes in dense cities; we quad-subdivide saturated cells
 * down to ~440 m (same idea as the McDonald's mainland grid crawler).
 *
 * API: POST https://mxsa.mxbc.net/api/v2/shopinfo/findNear
 *
 * Usage:
 *   node scripts/scrape-mixue.js                 # full mainland crawl
 *   node scripts/scrape-mixue.js --test-beijing  # one coarse cell in Beijing
 *   node scripts/scrape-mixue.js --test-guangzhou
 *   node scripts/scrape-mixue.js --resume        # continue from checkpoint
 *   node scripts/scrape-mixue.js --region east-south
 *
 * Output:
 *   frontend/public/data/locations/mixue.geojson
 *   data/mixue-checkpoint.json (gitignored)
 */

const fs = require("fs");
const path = require("path");
const { findNearStores } = require("./lib/mixue-api");

const REPO_ROOT = path.resolve(__dirname, "..");
const OUT_GEOJSON = path.join(
  REPO_ROOT,
  "frontend/public/data/locations/mixue.geojson"
);
const TEST_OUT_GEOJSON = path.join(
  REPO_ROOT,
  "data/mixue-test.geojson"
);
const CHECKPOINT_PATH = path.join(REPO_ROOT, "data/mixue-checkpoint.json");
const TEST_CHECKPOINT_PATH = path.join(REPO_ROOT, "data/mixue-test-checkpoint.json");
const CHAINS_JSON = path.join(REPO_ROOT, "frontend/public/data/chains.json");
const MANIFEST_JSON = path.join(REPO_ROOT, "frontend/public/data/manifest.json");

const CHECKPOINT_VERSION = 2;

const DEFAULT_DELAY_MS = 180;
const DEFAULT_DISTANCE_KM = 10;
const DEFAULT_LIMIT = 20;
const DEFAULT_WORKERS = 3;

// ~11 km coarse pass, then subdivide until ~440 m cells (20-result cap cannot hide gaps).
const INITIAL_GRID_STEP_DEGREES = 0.1;
const MIN_GRID_STEP_DEGREES = 0.004;
const EMPTY_CELL_SUBDIVIDE_MIN_STEP = 0.05;
const VISITED_PRECISION = 4;

const MAINLAND_BBOX = {
  minLat: 18.15,
  maxLat: 53.55,
  minLng: 73.66,
  maxLng: 134.77,
};

/** Optional --region filters (subset of mainland bbox). */
const REGION_FILTERS = {
  "east-south": { minLat: 20.0, maxLat: 42.0, minLng: 104.0, maxLng: 122.5 },
  northeast: { minLat: 38.5, maxLat: 53.2, minLng: 118.0, maxLng: 135.0 },
  southwest: { minLat: 21.0, maxLat: 34.0, minLng: 97.0, maxLng: 108.5 },
  northwest: { minLat: 35.0, maxLat: 49.5, minLng: 73.66, maxLng: 97.5 },
  "hainan-south": { minLat: 18.0, maxLat: 21.5, minLng: 108.5, maxLng: 111.5 },
  "north-central": { minLat: 37.0, maxLat: 45.0, minLng: 104.0, maxLng: 120.0 },
};

const TEST_BEIJING = {
  centerLat: 39.9042,
  centerLng: 116.4074,
  step: INITIAL_GRID_STEP_DEGREES,
};

const TEST_GUANGZHOU = {
  centerLat: 23.1291,
  centerLng: 113.2644,
  step: INITIAL_GRID_STEP_DEGREES,
};

function parseArgs(argv) {
  const args = {
    resume: false,
    testBeijing: false,
    testGuangzhou: false,
    region: null,
    delayMs: DEFAULT_DELAY_MS,
    distanceKm: DEFAULT_DISTANCE_KM,
    limit: DEFAULT_LIMIT,
    workers: DEFAULT_WORKERS,
    writePartial: true,
    maxPagesPerPoint: 3,
    verbose: false,
  };
  for (let i = 2; i < argv.length; i++) {
    const arg = argv[i];
    if (arg === "--resume") args.resume = true;
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
    else if (arg === "--delay") args.delayMs = Number(argv[++i]);
    else if (arg === "--distance") args.distanceKm = Number(argv[++i]);
    else if (arg === "--limit") args.limit = Number(argv[++i]);
    else if (arg === "--workers") args.workers = Number(argv[++i]);
    else if (arg === "--max-pages") args.maxPagesPerPoint = Number(argv[++i]);
    else if (arg === "--help" || arg === "-h") {
      console.log(`Usage: node scripts/scrape-mixue.js [options]

Adaptive grid (subdivides when a point returns ${DEFAULT_LIMIT} stores — API cap per point).

Options:
  --test-beijing     One coarse cell in central Beijing
  --test-guangzhou   One coarse cell in central Guangzhou (gap-fill sanity check)
  --resume           Continue from data/mixue-checkpoint.json
  --region NAME      Limit initial seed to a region (${Object.keys(REGION_FILTERS).join(", ")})
  --verbose          Log each API page / subdivision
  --workers N        Parallel grid workers (default ${DEFAULT_WORKERS})
  --delay MS         Delay between API calls per worker (default ${DEFAULT_DELAY_MS})
  --distance KM      Search radius per call (default ${DEFAULT_DISTANCE_KM})
  --limit N          Page size (default ${DEFAULT_LIMIT})
  --max-pages N      Max pages per point (default 3; page 2+ rarely adds new ids)
  --no-partial       Skip writing geojson until the end
`);
      process.exit(0);
    }
  }
  return args;
}

function isExcludedGridPoint(lat, lng) {
  // Hong Kong / Macau / Taiwan rough boxes
  if (lat >= 21.8 && lat <= 22.6 && lng >= 113.8 && lng <= 114.5) return true;
  if (lat >= 22.1 && lat <= 22.45 && lng >= 113.52 && lng <= 114.05) return true;
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

function iterInitialGrid(bbox, step = INITIAL_GRID_STEP_DEGREES) {
  const cells = [];
  for (let lat = bbox.minLat + step / 2; lat <= bbox.maxLat; lat += step) {
    for (let lng = bbox.minLng + step / 2; lng <= bbox.maxLng; lng += step) {
      if (isExcludedGridPoint(lat, lng)) continue;
      cells.push({
        lat: roundCoord(lat),
        lng: roundCoord(lng),
        step,
      });
    }
  }
  return cells;
}

function roundCoord(value) {
  return Math.round(value * 10 ** VISITED_PRECISION) / 10 ** VISITED_PRECISION;
}

function cellKey(cell) {
  return `${roundCoord(cell.lat)}|${roundCoord(cell.lng)}|${roundCoord(cell.step)}`;
}

function subdivideCell(lat, lng, step) {
  const quarter = step / 4;
  const halfStep = step / 2;
  const children = [];
  for (const dLat of [-quarter, quarter]) {
    for (const dLng of [-quarter, quarter]) {
      const childLat = roundCoord(lat + dLat);
      const childLng = roundCoord(lng + dLng);
      if (isExcludedGridPoint(childLat, childLng)) continue;
      children.push({ lat: childLat, lng: childLng, step: halfStep });
    }
  }
  return children;
}

function shouldSubdivide(shopCount, step, limit) {
  if (step <= MIN_GRID_STEP_DEGREES) return false;
  if (shopCount >= limit) return true;
  if (shopCount === 0 && step > EMPTY_CELL_SUBDIVIDE_MIN_STEP) return true;
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

function shopNumericId(shopId) {
  let hash = 0;
  for (const ch of String(shopId)) {
    hash = (hash * 31 + ch.charCodeAt(0)) >>> 0;
  }
  return hash || 1;
}

function shopToFeature(shop) {
  const id = shopNumericId(shop.shopId);
  return {
    type: "Feature",
    id,
    geometry: {
      type: "Point",
      coordinates: [shop.longitude, shop.latitude],
    },
    properties: {
      id,
      name: shop.shopName,
      chain_slug: "mixue",
      category_slug: "fast-food",
      address: shop.shopAddress || null,
      city: shop.regionName || null,
      shop_id: shop.shopId,
      shop_code: shop.shopCode || null,
    },
  };
}

function storesToGeojson(storesById) {
  const features = Object.values(storesById)
    .filter(isMainlandShop)
    .map(shopToFeature)
    .sort((a, b) => a.id - b.id);
  return { type: "FeatureCollection", features };
}

function emptyCheckpoint() {
  return {
    version: CHECKPOINT_VERSION,
    visited: [],
    queue: [],
    stores: {},
    stats: { apiCalls: 0, pages: 0, cellsProcessed: 0, subdivisions: 0 },
  };
}

function loadCheckpoint(checkpointPath = CHECKPOINT_PATH) {
  if (!fs.existsSync(checkpointPath)) {
    return emptyCheckpoint();
  }
  const raw = JSON.parse(fs.readFileSync(checkpointPath, "utf8"));
  if (raw.version !== CHECKPOINT_VERSION) {
    console.log(
      `Checkpoint v${raw.version ?? 1} → v${CHECKPOINT_VERSION}: keeping ${Object.keys(raw.stores || {}).length} stores, rebuilding adaptive queue`
    );
    return {
      version: CHECKPOINT_VERSION,
      visited: [],
      queue: [],
      stores: raw.stores || {},
      stats: {
        apiCalls: raw.stats?.apiCalls ?? 0,
        pages: raw.stats?.pages ?? 0,
        cellsProcessed: 0,
        subdivisions: 0,
      },
    };
  }
  return raw;
}

function saveCheckpoint(checkpoint, checkpointPath = CHECKPOINT_PATH) {
  fs.mkdirSync(path.dirname(checkpointPath), { recursive: true });
  fs.writeFileSync(checkpointPath, JSON.stringify(checkpoint, null, 0));
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
    existing.category_slug = "fast-food";
  } else {
    const maxId = chains.reduce((m, c) => Math.max(m, c.id || 0), 0);
    chains.push({
      id: maxId + 1,
      name: "蜜雪冰城 / Mixue",
      slug: "mixue",
      category_slug: "fast-food",
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

function seedCells(args) {
  if (args.testBeijing) {
    return [
      {
        lat: TEST_BEIJING.centerLat,
        lng: TEST_BEIJING.centerLng,
        step: TEST_BEIJING.step,
      },
    ];
  }
  if (args.testGuangzhou) {
    return [
      {
        lat: TEST_GUANGZHOU.centerLat,
        lng: TEST_GUANGZHOU.centerLng,
        step: TEST_GUANGZHOU.step,
      },
    ];
  }

  const bbox = args.region ? REGION_FILTERS[args.region] : MAINLAND_BBOX;
  if (!bbox) {
    throw new Error(`Unknown region: ${args.region}`);
  }
  return iterInitialGrid(bbox);
}

async function fetchAllPagesAtPoint(lat, lng, opts) {
  const shops = [];
  const seenAtPoint = new Set();
  let page = 1;
  while (true) {
    if (opts.verbose) {
      console.log(`    API page ${page} @ ${lat},${lng} step=${opts.cellStep} ...`);
    }
    const payload = await findNearStores({
      latitude: lat,
      longitude: lng,
      page,
      limit: opts.limit,
      distance: opts.distanceKm,
    });
    opts.checkpoint.stats.apiCalls += 1;
    opts.checkpoint.stats.pages += 1;

    if (payload.code !== 0) {
      throw new Error(
        `Mixue API error at (${lat},${lng}) page ${page}: code=${payload.code} msg=${payload.msg || ""}`
      );
    }

    const batch = (payload.data || []).filter(isMainlandShop);
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

async function run() {
  const args = parseArgs(process.argv);
  const isTest = args.testBeijing || args.testGuangzhou;
  const outGeojson = isTest ? TEST_OUT_GEOJSON : OUT_GEOJSON;
  const checkpointPath = isTest ? TEST_CHECKPOINT_PATH : CHECKPOINT_PATH;

  const checkpoint = args.resume && !isTest ? loadCheckpoint(checkpointPath) : emptyCheckpoint();
  const visited = new Set(checkpoint.visited || []);
  const queue = new WorkQueue(checkpoint.queue || []);

  if (queue.size === 0) {
    const seeds = seedCells(args);
    const regionBbox = args.region ? REGION_FILTERS[args.region] : null;
    const filtered = regionBbox
      ? seeds.filter((cell) => cellInBbox(cell.lat, cell.lng, regionBbox))
      : seeds;
    queue.pushMany(filtered);
    console.log(`Seeded ${filtered.length} coarse grid cells`);
  }

  console.log(
    `Mixue adaptive scrape: queue=${queue.size} visited=${visited.size} stores=${Object.keys(checkpoint.stores).length}`
  );
  if (args.testBeijing || args.testGuangzhou) {
    console.log("Test mode: single coarse cell with subdivision (verbose, 1 worker)");
    console.log(`Test output: ${path.relative(REPO_ROOT, outGeojson)} (does not touch production geojson)`);
  }

  let lastWrite = Date.now();
  let lastProgress = 0;

  async function processCell(cell) {
    const key = cellKey(cell);
    if (visited.has(key)) return null;
    visited.add(key);

    const shops = await fetchAllPagesAtPoint(cell.lat, cell.lng, {
      ...args,
      cellStep: cell.step,
      checkpoint,
    });

    let newGlobal = 0;
    for (const shop of shops) {
      if (!checkpoint.stores[shop.shopId]) newGlobal += 1;
      checkpoint.stores[shop.shopId] = shop;
    }

    checkpoint.stats.cellsProcessed += 1;

    let children = [];
    if (shouldSubdivide(shops.length, cell.step, args.limit)) {
      children = subdivideCell(cell.lat, cell.lng, cell.step);
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

  async function worker(workerId) {
    while (true) {
      const cell = queue.shift();
      if (!cell) return;

      const key = cellKey(cell);
      if (visited.has(key)) continue;

      try {
        const children = await processCell(cell);
        if (children && children.length > 0) {
          queue.pushMany(children);
        }
      } catch (err) {
        checkpoint.visited = Array.from(visited);
        checkpoint.queue = queue.items;
        saveCheckpoint(checkpoint, checkpointPath);
        throw err;
      }

      await sleep(args.delayMs);

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

      if (args.writePartial && Date.now() - lastWrite > 60_000) {
        const count = writeGeojson(checkpoint.stores, outGeojson);
        console.log(`\n  checkpoint write: ${count} features`);
        lastWrite = Date.now();
      }
    }
  }

  const workers = Math.max(1, args.workers);
  await Promise.all(Array.from({ length: workers }, (_, i) => worker(i + 1)));

  console.log("");
  checkpoint.visited = Array.from(visited);
  checkpoint.queue = [];
  saveCheckpoint(checkpoint, checkpointPath);
  const featureCount = writeGeojson(checkpoint.stores, outGeojson);
  if (!isTest) {
    updateManifestAndChains(featureCount);
  }
  console.log(
    `Done. ${featureCount} stores → ${path.relative(REPO_ROOT, outGeojson)}`
  );
  console.log(
    `Cells: ${checkpoint.stats.cellsProcessed}, subdivisions: ${checkpoint.stats.subdivisions}, API calls: ${checkpoint.stats.apiCalls}`
  );
}

run().catch((err) => {
  console.error(err);
  process.exit(1);
});
