import type { Category, Chain, LocationFeatureCollection, LocationProperties } from "./types";

const DATA_BASE = "/data";
/** Hard cap on markers drawn for the current map view. */
const MAX_BBOX_FEATURES = 40_000;
/** Per-chain cap — fixed so toggling filters does not inflate remaining chains. */
const PER_CHAIN_BUDGET = 3_000;

const chainCache = new Map<string, LocationFeatureCollection>();
let chainDataVersion: string | null = null;

async function fetchJson<T>(path: string, options?: { cache?: RequestCache }): Promise<T> {
  const response = await fetch(path, { cache: options?.cache ?? "default" });
  if (!response.ok) {
    throw new Error(`Failed to load ${path}: ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export async function loadCategories(): Promise<Category[]> {
  return fetchJson<Category[]>(`${DATA_BASE}/categories.json`, { cache: "no-store" });
}

export async function loadChains(category?: string): Promise<Chain[]> {
  const chains = await fetchJson<Chain[]>(`${DATA_BASE}/chains.json`, { cache: "no-store" });
  if (!category) {
    return chains;
  }
  return chains.filter((chain) => chain.category_slug === category);
}

export async function loadChainLocations(chainSlug: string): Promise<LocationFeatureCollection> {
  const manifest = await fetchJson<{ location_count?: number }>(`${DATA_BASE}/manifest.json`, {
    cache: "no-store"
  });
  const version = String(manifest.location_count ?? "");
  if (chainDataVersion !== version) {
    chainCache.clear();
    chainDataVersion = version;
  }

  const cached = chainCache.get(chainSlug);
  if (cached) {
    return cached;
  }
  const collection = await fetchJson<LocationFeatureCollection>(
    `${DATA_BASE}/locations/${encodeURIComponent(chainSlug)}.geojson?v=${encodeURIComponent(version)}`,
    { cache: "no-store" }
  );
  chainCache.set(chainSlug, collection);
  return collection;
}

function featureInBbox(
  lng: number,
  lat: number,
  minLng: number,
  minLat: number,
  maxLng: number,
  maxLat: number
): boolean {
  return lng >= minLng && lng <= maxLng && lat >= minLat && lat <= maxLat;
}

function thinFeatures(
  features: LocationFeatureCollection["features"],
  minLng: number,
  minLat: number,
  maxLng: number,
  maxLat: number,
  maxFeatures: number = MAX_BBOX_FEATURES
): LocationFeatureCollection["features"] {
  if (features.length <= maxFeatures) {
    return features;
  }

  const width = Math.max(maxLng - minLng, 0.001);
  const height = Math.max(maxLat - minLat, 0.001);
  const gridDeg = Math.max(Math.sqrt((width * height) / maxFeatures) * 0.9, 0.002);
  const cells = new Map<string, (typeof features)[number]>();

  const sorted = [...features].sort(
    (left, right) => (left.properties?.id ?? 0) - (right.properties?.id ?? 0)
  );

  for (const feature of sorted) {
    if (feature.geometry.type !== "Point") {
      continue;
    }
    const [lng, lat] = feature.geometry.coordinates;
    const key = `${Math.floor(lng / gridDeg)}:${Math.floor(lat / gridDeg)}`;
    if (!cells.has(key)) {
      cells.set(key, feature);
    }
  }

  return Array.from(cells.values()).slice(0, maxFeatures);
}

/** Round-robin merge so one chain does not paint over every other at overlaps. */
function interleaveChainFeatures(
  perChainFeatures: LocationFeatureCollection["features"][]
): LocationFeatureCollection["features"] {
  const merged: LocationFeatureCollection["features"] = [];
  const indices = new Array(perChainFeatures.length).fill(0);

  let remaining = perChainFeatures.reduce((sum, features) => sum + features.length, 0);
  while (remaining > 0) {
    for (let chainIndex = 0; chainIndex < perChainFeatures.length; chainIndex++) {
      const features = perChainFeatures[chainIndex];
      const index = indices[chainIndex];
      if (index >= features.length) {
        continue;
      }

      merged.push(features[index]);
      indices[chainIndex] += 1;
      remaining -= 1;
    }
  }

  return merged;
}

function capCombinedFeatures(
  perChainFeatures: LocationFeatureCollection["features"][],
  maxTotal: number
): LocationFeatureCollection["features"] {
  let cappedPerChain = perChainFeatures;

  while (true) {
    const merged = interleaveChainFeatures(cappedPerChain);
    if (merged.length <= maxTotal) {
      return merged;
    }

    const total = cappedPerChain.reduce((sum, features) => sum + features.length, 0);
    if (total === 0) {
      return merged.slice(0, maxTotal);
    }

    const ratio = maxTotal / total;
    const next = cappedPerChain.map((features) => {
      if (features.length === 0) {
        return features;
      }
      return features.slice(0, Math.max(1, Math.floor(features.length * ratio)));
    });

    if (next.every((features, index) => features.length === cappedPerChain[index].length)) {
      return interleaveChainFeatures(next).slice(0, maxTotal);
    }

    cappedPerChain = next;
  }
}

export async function loadLocationsForBbox(params: {
  minLng: number;
  minLat: number;
  maxLng: number;
  maxLat: number;
  chains: string[];
}): Promise<LocationFeatureCollection> {
  if (params.chains.length === 0) {
    return { type: "FeatureCollection", features: [] };
  }

  const chainSlugs = [...params.chains].sort();
  const collections = await Promise.all(chainSlugs.map((slug) => loadChainLocations(slug)));
  const perChainInBbox = collections.map((collection) =>
    collection.features.filter((feature) => {
      if (feature.geometry.type !== "Point") {
        return false;
      }
      const [lng, lat] = feature.geometry.coordinates;
      return featureInBbox(lng, lat, params.minLng, params.minLat, params.maxLng, params.maxLat);
    })
  );

  const perChainThinned = perChainInBbox.map((features) =>
    thinFeatures(
      features,
      params.minLng,
      params.minLat,
      params.maxLng,
      params.maxLat,
      PER_CHAIN_BUDGET
    )
  );

  return {
    type: "FeatureCollection",
    features: capCombinedFeatures(perChainThinned, MAX_BBOX_FEATURES)
  };
}

export async function searchLocations(q: string): Promise<LocationFeatureCollection> {
  const chains = await loadChains();
  const pattern = q.trim().toLowerCase();
  if (!pattern) {
    return { type: "FeatureCollection", features: [] };
  }

  const collections = await Promise.all(chains.map((chain) => loadChainLocations(chain.slug)));
  const matches: LocationFeatureCollection["features"] = [];

  for (const collection of collections) {
    for (const feature of collection.features) {
      const props = feature.properties as LocationProperties;
      const haystack = [props.name, props.address, props.city]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      if (haystack.includes(pattern)) {
        matches.push(feature);
        if (matches.length >= 100) {
          return { type: "FeatureCollection", features: matches };
        }
      }
    }
  }

  return { type: "FeatureCollection", features: matches };
}
