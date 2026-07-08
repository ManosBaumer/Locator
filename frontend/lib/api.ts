import type { Category, Chain, LocationFeatureCollection } from "./types";

// Same-origin requests are proxied by Next.js route handlers in development.
const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "";

export async function getCategories(): Promise<Category[]> {
  return getJson<Category[]>("/api/v1/categories");
}

export async function getChains(category?: string): Promise<Chain[]> {
  const params = new URLSearchParams();
  if (category) {
    params.set("category", category);
  }
  return getJson<Chain[]>(`/api/v1/chains${params.size ? `?${params}` : ""}`);
}

export async function getLocationsForBbox(params: {
  minLng: number;
  minLat: number;
  maxLng: number;
  maxLat: number;
  chains: string[];
}): Promise<LocationFeatureCollection> {
  const query = new URLSearchParams({
    min_lng: String(params.minLng),
    min_lat: String(params.minLat),
    max_lng: String(params.maxLng),
    max_lat: String(params.maxLat)
  });
  if (params.chains.length) {
    query.set("chains", params.chains.join(","));
  }
  return getJson<LocationFeatureCollection>(`/api/v1/locations/bbox?${query}`);
}

export async function searchLocations(q: string): Promise<LocationFeatureCollection> {
  const query = new URLSearchParams({ q });
  return getJson<LocationFeatureCollection>(`/api/v1/locations/search?${query}`);
}

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`API request failed: ${response.status} ${response.statusText}`);
  }
  return response.json() as Promise<T>;
}
