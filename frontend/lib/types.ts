import type { FeatureCollection, Point } from "geojson";

export type Category = {
  id: number;
  name: string;
  slug: string;
};

export type Chain = {
  id: number;
  name: string;
  slug: string;
  category_slug: string;
  location_count: number;
};

export type LocationProperties = {
  id: number;
  name: string | null;
  chain_slug: string;
  category_slug: string;
  address: string | null;
  city: string | null;
};

export type LocationFeatureCollection = FeatureCollection<Point, LocationProperties>;
