"use client";

import { getLocationsForBbox } from "@/lib/api";
import { CHAIN_ICON_IMAGE_EXPRESSION, loadChainMarkerImages } from "@/lib/chain-logos";
import { enableEaseWheelZoom } from "@/lib/ease-wheel-zoom";
import type { LocationFeatureCollection, LocationProperties } from "@/lib/types";
import maplibregl, { GeoJSONSource, Map as MapLibreMap } from "maplibre-gl";
import { memo, useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { LocationPopup } from "./LocationPopup";

type Props = {
  selectedChains: string[];
};

const DEFAULT_CENTER: [number, number] = [104.1954, 35.8617];
const DEFAULT_ZOOM = 3.7;
const DATA_DEBOUNCE_MS = 600;
const SOURCE_ID = "locations";
const POINTS_LAYER = "location-points";

const EMPTY_COLLECTION: LocationFeatureCollection = {
  type: "FeatureCollection",
  features: []
};

function setSourceData(map: MapLibreMap, data: LocationFeatureCollection): boolean {
  const source = map.getSource(SOURCE_ID) as GeoJSONSource | undefined;
  if (!source) {
    return false;
  }
  source.setData(data);
  return true;
}

function addLocationLayers(map: MapLibreMap) {
  map.addSource(SOURCE_ID, {
    type: "geojson",
    data: EMPTY_COLLECTION,
    promoteId: "id"
  });

  map.addLayer({
    id: POINTS_LAYER,
    type: "symbol",
    source: SOURCE_ID,
    layout: {
      "icon-image": CHAIN_ICON_IMAGE_EXPRESSION as unknown as string,
      "icon-size": 0.5,
      "icon-allow-overlap": true,
      "icon-ignore-placement": true
    }
  });
}

function bindLocationInteractions(
  map: MapLibreMap,
  getPropertiesById: () => globalThis.Map<number, LocationProperties>
) {
  map.on("mouseenter", POINTS_LAYER, () => {
    map.getCanvas().style.cursor = "pointer";
  });
  map.on("mouseleave", POINTS_LAYER, () => {
    map.getCanvas().style.cursor = "";
  });

  map.on("click", POINTS_LAYER, (event) => {
    const feature = event.features?.[0];
    if (!feature || feature.geometry.type !== "Point") {
      return;
    }

    const [lng, lat] = feature.geometry.coordinates;
    const rawId = feature.id ?? feature.properties?.id;
    const featureId = typeof rawId === "number" ? rawId : Number(rawId);
    const location =
      (Number.isFinite(featureId) ? getPropertiesById().get(featureId) : undefined) ??
      (feature.properties as LocationProperties);
    const popupNode = document.createElement("div");
    createRoot(popupNode).render(<LocationPopup location={location} />);
    new maplibregl.Popup({ offset: 16, closeButton: true })
      .setLngLat([lng, lat])
      .setDOMContent(popupNode)
      .addTo(map);
  });
}

export const Map = memo(function Map({ selectedChains }: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const featuresRef = useRef<LocationFeatureCollection>(EMPTY_COLLECTION);
  const propertiesByIdRef = useRef<globalThis.Map<number, LocationProperties>>(new globalThis.Map());
  const selectedChainsRef = useRef(selectedChains);
  const dataTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [features, setFeatures] = useState<LocationFeatureCollection>(EMPTY_COLLECTION);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    selectedChainsRef.current = selectedChains;
  }, [selectedChains]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !map.isStyleLoaded()) {
      return;
    }
    setSourceData(map, features);
  }, [features]);

  async function loadBounds() {
    const map = mapRef.current;
    if (!map) {
      return;
    }

    if (selectedChainsRef.current.length === 0) {
      if (featuresRef.current.features.length > 0) {
        featuresRef.current = EMPTY_COLLECTION;
        propertiesByIdRef.current = new globalThis.Map();
        setFeatures(EMPTY_COLLECTION);
        setSourceData(map, EMPTY_COLLECTION);
      }
      setError(null);
      return;
    }

    const bounds = map.getBounds();
    try {
      const collection = await getLocationsForBbox({
        minLng: bounds.getWest(),
        minLat: bounds.getSouth(),
        maxLng: bounds.getEast(),
        maxLat: bounds.getNorth(),
        chains: selectedChainsRef.current
      });
      featuresRef.current = collection;
      propertiesByIdRef.current = new globalThis.Map(
        collection.features.map((feature) => [feature.properties.id, feature.properties])
      );
      setFeatures(collection);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load locations");
    }
  }

  function scheduleDataRefresh() {
    if (selectedChainsRef.current.length === 0) {
      return;
    }

    if (dataTimeoutRef.current) {
      clearTimeout(dataTimeoutRef.current);
    }

    dataTimeoutRef.current = setTimeout(() => {
      const map = mapRef.current;
      if (!map || map.isMoving() || map.isZooming()) {
        scheduleDataRefresh();
        return;
      }

      void loadBounds();
    }, DATA_DEBOUNCE_MS);
  }

  useEffect(() => {
    if (!containerRef.current || mapRef.current) {
      return;
    }

    const map = new maplibregl.Map({
      container: containerRef.current,
      style: process.env.NEXT_PUBLIC_MAP_TILE_URL ?? "https://tiles.openfreemap.org/styles/liberty",
      center: DEFAULT_CENTER,
      zoom: DEFAULT_ZOOM,
      maxTileCacheSize: 512
    });

    map.addControl(new maplibregl.NavigationControl(), "top-right");
    mapRef.current = map;

    const disableEaseWheelZoom = enableEaseWheelZoom(map);

    map.on("load", () => {
      void loadChainMarkerImages(map)
        .catch(() => undefined)
        .finally(() => {
          addLocationLayers(map);
          bindLocationInteractions(map, () => propertiesByIdRef.current);
          setSourceData(map, featuresRef.current);
          void loadBounds();
        });
    });

    map.on("moveend", scheduleDataRefresh);

    return () => {
      disableEaseWheelZoom();
      if (dataTimeoutRef.current) {
        clearTimeout(dataTimeoutRef.current);
      }
      map.remove();
      mapRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (mapRef.current) {
      void loadBounds();
    }
  }, [selectedChains]);

  return (
    <div className="relative h-full min-h-0 overflow-hidden rounded-3xl bg-slate-200">
      <div ref={containerRef} className="absolute inset-0" />
      {error ? (
        <div className="absolute left-4 top-4 rounded-xl bg-white px-4 py-3 text-sm text-red-700 shadow">
          {error}
        </div>
      ) : null}
    </div>
  );
});
