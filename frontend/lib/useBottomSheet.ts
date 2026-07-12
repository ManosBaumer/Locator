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

/** Visible peek height when the sheet is at its minimum. */
const MIN_SHEET_HEIGHT_PX = 92;
/** Max sheet height as a fraction of the viewport (slightly taller than before). */
const MAX_SHEET_VH = 0.78;

type DragState = {
  pointerId: number;
  startY: number;
  originHeight: number;
};

function computeMaxHeight(): number {
  if (typeof window === "undefined") {
    return MIN_SHEET_HEIGHT_PX;
  }
  return Math.round(window.innerHeight * MAX_SHEET_VH);
}

function clampHeight(height: number, max: number): number {
  return Math.min(Math.max(height, MIN_SHEET_HEIGHT_PX), max);
}

export function useBottomSheet() {
  const [sheetHeight, setSheetHeight] = useState(MIN_SHEET_HEIGHT_PX);
  const [maxHeight, setMaxHeight] = useState(MIN_SHEET_HEIGHT_PX);
  const [isDragging, setIsDragging] = useState(false);
  const [isReady, setIsReady] = useState(false);
  const dragStateRef = useRef<DragState | null>(null);
  const sheetHeightRef = useRef(sheetHeight);
  const maxHeightRef = useRef(maxHeight);

  useEffect(() => {
    sheetHeightRef.current = sheetHeight;
  }, [sheetHeight]);

  useEffect(() => {
    maxHeightRef.current = maxHeight;
  }, [maxHeight]);

  const refreshMetrics = useCallback(() => {
    const max = computeMaxHeight();
    setMaxHeight(max);
    maxHeightRef.current = max;
    setSheetHeight((current) => clampHeight(current, max));
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
      setSheetHeight(clampHeight(dragState.originHeight - deltaY, maxHeightRef.current));
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
    sheetHeight > MIN_SHEET_HEIGHT_PX + (maxHeight - MIN_SHEET_HEIGHT_PX) * 0.08;

  return {
    sheetHeight,
    isDragging,
    isExpanded,
    sheetStyle,
    dragHandleProps,
    minHeight: MIN_SHEET_HEIGHT_PX,
    maxHeight
  };
};
