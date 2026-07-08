import {
  loadCategories,
  loadChains,
  loadLocationsForBbox,
  searchLocations as searchStaticLocations
} from "./static-data";
import type { Category, Chain, LocationFeatureCollection } from "./types";

export async function getCategories(): Promise<Category[]> {
  return loadCategories();
}

export async function getChains(category?: string): Promise<Chain[]> {
  return loadChains(category);
}

export async function getLocationsForBbox(params: {
  minLng: number;
  minLat: number;
  maxLng: number;
  maxLat: number;
  chains: string[];
}): Promise<LocationFeatureCollection> {
  return loadLocationsForBbox(params);
}

export async function searchLocations(q: string): Promise<LocationFeatureCollection> {
  return searchStaticLocations(q);
}
