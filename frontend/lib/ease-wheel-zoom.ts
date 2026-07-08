import type { Map as MapLibreMap } from "maplibre-gl";

type Options = {
  /** Zoom levels per wheel notch — matches NavigationControl (+/- 1). */
  step?: number;
  /** Animation length in ms — matches NavigationControl easeTo. */
  duration?: number;
};

/**
 * MapLibre's built-in scrollZoom uses a separate render-loop path that can
 * stutter at tile zoom boundaries. NavigationControl buttons call easeTo()
 * instead, which users perceive as much smoother — so we route wheel input
 * through the same API.
 */
export function enableEaseWheelZoom(map: MapLibreMap, options: Options = {}): () => void {
  const step = options.step ?? 1;
  const duration = options.duration ?? 300;

  map.scrollZoom.disable();

  const canvas = map.getCanvas();

  const onWheel = (event: WheelEvent) => {
    event.preventDefault();

    const rect = canvas.getBoundingClientRect();
    const around = map.unproject([event.clientX - rect.left, event.clientY - rect.top]);

    let delta = event.deltaY;
    if (event.deltaMode === WheelEvent.DOM_DELTA_LINE) {
      delta *= 40;
    }

    if (delta === 0) {
      return;
    }

    // Trackpads emit small continuous deltas; mice emit large discrete ones.
    const isTrackpad = Math.abs(delta) < 50;
    let zoomDelta: number;

    if (isTrackpad) {
      zoomDelta = -delta * 0.01;
    } else {
      const notches = Math.min(3, Math.max(1, Math.round(Math.abs(delta) / 100)));
      zoomDelta = (delta > 0 ? -1 : 1) * step * notches;
    }

    if (event.shiftKey) {
      zoomDelta /= 4;
    }

    const nextZoom = Math.min(map.getMaxZoom(), Math.max(map.getMinZoom(), map.getZoom() + zoomDelta));

    map.easeTo({
      zoom: nextZoom,
      around: [around.lng, around.lat],
      duration: isTrackpad ? 0 : duration,
      essential: true
    });
  };

  canvas.addEventListener("wheel", onWheel, { passive: false });

  return () => {
    canvas.removeEventListener("wheel", onWheel);
    map.scrollZoom.enable();
  };
}
