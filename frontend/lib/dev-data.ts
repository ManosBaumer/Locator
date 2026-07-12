import type { Category, Chain, LocationFeatureCollection } from "./types";

const categories: Category[] = [{ id: 1, name: "Supermarkets", slug: "supermarket" }];

const chains: Chain[] = [
  {
    id: 1,
    name: "盒马 / Freshippo",
    slug: "hema",
    category_slug: "supermarket",
    location_count: 3
  }
];

const locations: LocationFeatureCollection = {
  type: "FeatureCollection",
  features: [
    {
      type: "Feature",
      id: 1,
      geometry: { type: "Point", coordinates: [121.5828, 31.2445] },
      properties: {
        id: 1,
        name: "盒马鲜生 上海金桥店",
        chain_slug: "hema",
        category_slug: "supermarket",
        address: "上海市浦东新区张杨路3611弄金桥国际商业广场",
        city: "上海市"
      }
    },
    {
      type: "Feature",
      id: 2,
      geometry: { type: "Point", coordinates: [116.4994, 39.9211] },
      properties: {
        id: 2,
        name: "盒马鲜生 北京十里堡店",
        chain_slug: "hema",
        category_slug: "supermarket",
        address: "北京市朝阳区十里堡乙2号院",
        city: "北京市"
      }
    },
    {
      type: "Feature",
      id: 3,
      geometry: { type: "Point", coordinates: [113.9308, 22.5054] },
      properties: {
        id: 3,
        name: "盒马鲜生 深圳南山店",
        chain_slug: "hema",
        category_slug: "supermarket",
        address: "深圳市南山区中心路宝能太古城",
        city: "深圳市"
      }
    }
  ]
};

function inBbox(
  lng: number,
  lat: number,
  minLng: number,
  minLat: number,
  maxLng: number,
  maxLat: number
): boolean {
  return lng >= minLng && lng <= maxLng && lat >= minLat && lat <= maxLat;
}

export function getDevResponse(path: string, params: URLSearchParams): unknown | null {
  if (path === "categories") {
    return categories;
  }

  if (path === "chains") {
    const category = params.get("category");
    if (!category) {
      return chains;
    }
    return chains.filter((chain) => chain.category_slug === category);
  }

  if (path === "locations/bbox") {
    const minLng = Number(params.get("min_lng"));
    const minLat = Number(params.get("min_lat"));
    const maxLng = Number(params.get("max_lng"));
    const maxLat = Number(params.get("max_lat"));
    const chainFilter = (params.get("chains") ?? "").split(",").filter(Boolean);

    if (chainFilter.length === 0) {
      return { type: "FeatureCollection", features: [] };
    }

    const features = locations.features.filter((feature) => {
      const [lng, lat] = feature.geometry.coordinates;
      if (!inBbox(lng, lat, minLng, minLat, maxLng, maxLat)) {
        return false;
      }
      if (!chainFilter.includes(feature.properties.chain_slug)) {
        return false;
      }
      return true;
    });

    return { type: "FeatureCollection", features };
  }

  if (path === "locations/search") {
    const query = (params.get("q") ?? "").trim().toLowerCase();
    if (!query) {
      return locations;
    }

    const features = locations.features.filter((feature) => {
      const haystack = [
        feature.properties.name,
        feature.properties.address,
        feature.properties.city,
        feature.properties.chain_slug
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      return haystack.includes(query);
    });

    return { type: "FeatureCollection", features };
  }

  if (path === "locations/nearby") {
    return locations;
  }

  if (path.startsWith("chains/") && path.endsWith("/locations")) {
    return locations.features.map((feature) => ({
      id: feature.properties.id,
      external_id: `hema-seed-${feature.properties.id}`,
      name: feature.properties.name,
      address: feature.properties.address,
      city: feature.properties.city,
      chain_slug: feature.properties.chain_slug,
      latitude: feature.geometry.coordinates[1],
      longitude: feature.geometry.coordinates[0],
      coordinate_system: "GCJ02"
    }));
  }

  return null;
}
