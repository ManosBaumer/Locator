import type { Category, Chain, LocationFeatureCollection, LocationProperties } from "./types";

const DATA_BASE = "/data";
const MAX_BBOX_FEATURES = 10_000;

const chainCache = new Map<string, LocationFeatureCollection>();

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
  const cached = chainCache.get(chainSlug);
  if (cached) {
    return cached;
  }
  const collection = await fetchJson<LocationFeatureCollection>(
    `${DATA_BASE}/locations/${encodeURIComponent(chainSlug)}.geojson`,
    { cache: "force-cache" }
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
  maxLat: number
): LocationFeatureCollection["features"] {
  if (features.length <= MAX_BBOX_FEATURES) {
    return features;
  }

  const width = Math.max(maxLng - minLng, 0.001);
  const height = Math.max(maxLat - minLat, 0.001);
  const gridDeg = Math.max(Math.sqrt((width * height) / MAX_BBOX_FEATURES) * 0.9, 0.002);
  const cells = new Map<string, (typeof features)[number]>();

  for (const feature of features) {
    if (feature.geometry.type !== "Point") {
      continue;
    }
    const [lng, lat] = feature.geometry.coordinates;
    const key = `${Math.floor(lng / gridDeg)}:${Math.floor(lat / gridDeg)}`;
    if (!cells.has(key)) {
      cells.set(key, feature);
    }
  }

  return Array.from(cells.values()).slice(0, MAX_BBOX_FEATURES);
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

  const collections = await Promise.all(params.chains.map((slug) => loadChainLocations(slug)));
  const inBbox = collections.flatMap((collection) =>
    collection.features.filter((feature) => {
      if (feature.geometry.type !== "Point") {
        return false;
      }
      const [lng, lat] = feature.geometry.coordinates;
      return featureInBbox(lng, lat, params.minLng, params.minLat, params.maxLng, params.maxLat);
    })
  );

  return {
    type: "FeatureCollection",
    features: thinFeatures(inBbox, params.minLng, params.minLat, params.maxLng, params.maxLat)
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
