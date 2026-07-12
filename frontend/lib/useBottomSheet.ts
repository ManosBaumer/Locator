"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type HTMLAttributes,
  type PointerEvent as ReactPointerEvent
} from "react";

/** Fallback peek height before the panel header is measured. */
const MIN_SHEET_HEIGHT_PX = 80;
/** Max sheet height as a fraction of the viewport (slightly taller than before). */
const MAX_SHEET_VH = 0.78;

type DragState = {
  pointerId: number;
  startY: number;
  originHeight: number;
};

function computeMaxHeight(minHeight: number): number {
  if (typeof window === "undefined") {
    return minHeight;
  }
  return Math.round(window.innerHeight * MAX_SHEET_VH);
}

function clampHeight(height: number, min: number, max: number): number {
  return Math.min(Math.max(height, min), max);
}

export function useBottomSheet() {
  const [minSheetHeight, setMinSheetHeightState] = useState(MIN_SHEET_HEIGHT_PX);
  const [sheetHeight, setSheetHeight] = useState(MIN_SHEET_HEIGHT_PX);
  const [maxHeight, setMaxHeight] = useState(MIN_SHEET_HEIGHT_PX);
  const [isDragging, setIsDragging] = useState(false);
  const [isReady, setIsReady] = useState(false);
  const dragStateRef = useRef<DragState | null>(null);
  const sheetHeightRef = useRef(sheetHeight);
  const maxHeightRef = useRef(maxHeight);
  const minHeightRef = useRef(minSheetHeight);

  useEffect(() => {
    sheetHeightRef.current = sheetHeight;
  }, [sheetHeight]);

  useEffect(() => {
    maxHeightRef.current = maxHeight;
  }, [maxHeight]);

  useEffect(() => {
    minHeightRef.current = minSheetHeight;
  }, [minSheetHeight]);

  const setMinSheetHeight = useCallback((height: number) => {
    const nextMin = Math.ceil(height);
    if (nextMin === minHeightRef.current) {
      return;
    }

    const previousMin = minHeightRef.current;
    minHeightRef.current = nextMin;
    setMinSheetHeightState(nextMin);
    setSheetHeight((current) => {
      if (current <= previousMin + 2) {
        return nextMin;
      }
      return clampHeight(current, nextMin, maxHeightRef.current);
    });
  }, []);

  const refreshMetrics = useCallback(() => {
    const min = minHeightRef.current;
    const max = computeMaxHeight(min);
    setMaxHeight(max);
    maxHeightRef.current = max;
    setSheetHeight((current) => clampHeight(current, min, max));
    setIsReady(true);
  }, []);

  useEffect(() => {
    refreshMetrics();
    window.addEventListener("resize", refreshMetrics);
    return () => window.removeEventListener("resize", refreshMetrics);
  }, [refreshMetrics]);

  useEffect(() => {
    if (!isDragging) {
      return;
    }

    function handlePointerMove(event: PointerEvent) {
      const dragState = dragStateRef.current;
      if (!dragState || dragState.pointerId !== event.pointerId) {
        return;
      }

      const deltaY = event.clientY - dragState.startY;
      setSheetHeight(
        clampHeight(
          dragState.originHeight - deltaY,
          minHeightRef.current,
          maxHeightRef.current
        )
      );
    }

    function endDrag(event: PointerEvent) {
      const dragState = dragStateRef.current;
      if (!dragState || dragState.pointerId !== event.pointerId) {
        return;
      }

      dragStateRef.current = null;
      setIsDragging(false);
    }

    window.addEventListener("pointermove", handlePointerMove);
    window.addEventListener("pointerup", endDrag);
    window.addEventListener("pointercancel", endDrag);

    return () => {
      window.removeEventListener("pointermove", handlePointerMove);
      window.removeEventListener("pointerup", endDrag);
      window.removeEventListener("pointercancel", endDrag);
    };
  }, [isDragging]);

  const handlePointerDown = useCallback((event: ReactPointerEvent<HTMLElement>) => {
    if (event.button !== 0) {
      return;
    }

    event.preventDefault();

    dragStateRef.current = {
      pointerId: event.pointerId,
      startY: event.clientY,
      originHeight: sheetHeightRef.current
    };

    setIsDragging(true);
    event.currentTarget.setPointerCapture(event.pointerId);
  }, []);

  const handlePointerUp = useCallback((event: ReactPointerEvent<HTMLElement>) => {
    if (dragStateRef.current?.pointerId !== event.pointerId) {
      return;
    }

    dragStateRef.current = null;
    setIsDragging(false);
    event.currentTarget.releasePointerCapture(event.pointerId);
  }, []);

  const dragHandleProps: HTMLAttributes<HTMLElement> = useMemo(
    () => ({
      onPointerDown: handlePointerDown,
      onPointerUp: handlePointerUp,
      className: isDragging ? "cursor-grabbing touch-none select-none" : "cursor-grab touch-none select-none"
    }),
    [handlePointerDown, handlePointerUp, isDragging]
  );

  const sheetStyle: CSSProperties = {
    height: sheetHeight,
    visibility: isReady ? "visible" : "hidden"
  };

  const isExpanded =
    sheetHeight > minSheetHeight + (maxHeight - minSheetHeight) * 0.08;

  return {
    sheetHeight,
    isDragging,
    isExpanded,
    sheetStyle,
    dragHandleProps,
    minHeight: minSheetHeight,
    maxHeight,
    setMinSheetHeight
  };
};
