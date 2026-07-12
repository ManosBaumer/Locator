"use client";

import { loadLocationsForBbox } from "@/lib/static-data";
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
/** Prevent zooming out far enough for the world to repeat (duplicates markers). */
const MIN_ZOOM = 3;
const DATA_DEBOUNCE_MS = 250;
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

function chainsKey(chains: string[]): string {
  return [...chains].sort().join("\0");
}

export const Map = memo(function Map({ selectedChains }: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const featuresRef = useRef<LocationFeatureCollection>(EMPTY_COLLECTION);
  const propertiesByIdRef = useRef<globalThis.Map<number, LocationProperties>>(new globalThis.Map());
  const selectedChainsRef = useRef(selectedChains);
  const dataTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const loadGenerationRef = useRef(0);
  const [error, setError] = useState<string | null>(null);
  const selectedChainsKey = chainsKey(selectedChains);

  useEffect(() => {
    selectedChainsRef.current = selectedChains;
  }, [selectedChains]);

  async function loadBounds() {
    const map = mapRef.current;
    if (!map) {
      return;
    }

    if (selectedChainsRef.current.length === 0) {
      if (featuresRef.current.features.length > 0) {
        featuresRef.current = EMPTY_COLLECTION;
        propertiesByIdRef.current = new globalThis.Map();
        setSourceData(map, EMPTY_COLLECTION);
      }
      setError(null);
      return;
    }

    const bounds = map.getBounds();
    const generation = ++loadGenerationRef.current;
    try {
      const collection = await loadLocationsForBbox({
        minLng: bounds.getWest(),
        minLat: bounds.getSouth(),
        maxLng: bounds.getEast(),
        maxLat: bounds.getNorth(),
        chains: selectedChainsRef.current
      });
      if (generation !== loadGenerationRef.current) {
        return;
      }
      featuresRef.current = collection;
      propertiesByIdRef.current = new globalThis.Map(
        collection.features.map((feature) => [feature.properties.id, feature.properties])
      );
      setSourceData(map, collection);
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
      minZoom: MIN_ZOOM,
      renderWorldCopies: false,
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
  }, [selectedChainsKey]);

  return (
    <div className="absolute inset-0 h-full w-full">
      <div ref={containerRef} className="absolute inset-0" />
      {error ? (
        <div className="glass-panel absolute bottom-4 left-1/2 z-10 max-w-md -translate-x-1/2 rounded-xl px-4 py-3 text-sm text-red-800">
          {error}
        </div>
      ) : null}
    </div>
  );
}, chainsKeyEqual);

function chainsKeyEqual(prev: Props, next: Props): boolean {
  return chainsKey(prev.selectedChains) === chainsKey(next.selectedChains);
}
