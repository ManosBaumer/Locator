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

export type BottomSheetSnap = "collapsed" | "expanded";

const COLLAPSED_HEIGHT_PX = 76;
const EXPANDED_VH = 0.62;

type DragState = {
  pointerId: number;
  startY: number;
  originTranslateY: number;
};

function expandedHeightPx(): number {
  return Math.round(window.innerHeight * EXPANDED_VH);
}

function hiddenOffsetPx(): number {
  return Math.max(0, expandedHeightPx() - COLLAPSED_HEIGHT_PX);
}

function snapTranslateY(snap: BottomSheetSnap): number {
  return snap === "collapsed" ? hiddenOffsetPx() : 0;
}

export function useBottomSheet(initialSnap: BottomSheetSnap = "collapsed") {
  const [snap, setSnap] = useState<BottomSheetSnap>(initialSnap);
  const [translateY, setTranslateY] = useState(0);
  const [expandedHeight, setExpandedHeight] = useState(COLLAPSED_HEIGHT_PX);
  const [isDragging, setIsDragging] = useState(false);
  const [isReady, setIsReady] = useState(false);
  const dragStateRef = useRef<DragState | null>(null);
  const translateYRef = useRef(translateY);

  useEffect(() => {
    translateYRef.current = translateY;
  }, [translateY]);

  const refreshMetrics = useCallback(() => {
    const nextExpanded = expandedHeightPx();
    setExpandedHeight(nextExpanded);
    setTranslateY(snapTranslateY(snap));
    setIsReady(true);
  }, [snap]);

  useEffect(() => {
    refreshMetrics();
    window.addEventListener("resize", refreshMetrics);
    return () => window.removeEventListener("resize", refreshMetrics);
  }, [refreshMetrics]);

  useEffect(() => {
    if (!isDragging) {
      setTranslateY(snapTranslateY(snap));
    }
  }, [snap, isDragging]);

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
      const hidden = hiddenOffsetPx();
      setTranslateY(Math.min(Math.max(dragState.originTranslateY + deltaY, 0), hidden));
    }

    function endDrag(event: PointerEvent) {
      const dragState = dragStateRef.current;
      if (!dragState || dragState.pointerId !== event.pointerId) {
        return;
      }

      const hidden = hiddenOffsetPx();
      const current = translateYRef.current;
      dragStateRef.current = null;
      setIsDragging(false);
      setSnap(current < hidden / 2 ? "expanded" : "collapsed");
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
      originTranslateY: translateYRef.current
    };

    setIsDragging(true);
    event.currentTarget.setPointerCapture(event.pointerId);
  }, []);

  const handlePointerUp = useCallback((event: ReactPointerEvent<HTMLElement>) => {
    if (dragStateRef.current?.pointerId !== event.pointerId) {
      return;
    }

    const hidden = hiddenOffsetPx();
    const current = translateYRef.current;
    dragStateRef.current = null;
    setIsDragging(false);
    setSnap(current < hidden / 2 ? "expanded" : "collapsed");
    event.currentTarget.releasePointerCapture(event.pointerId);
  }, []);

  const handleProps: HTMLAttributes<HTMLElement> = useMemo(
    () => ({
      onPointerDown: handlePointerDown,
      onPointerUp: handlePointerUp,
      className: isDragging ? "cursor-grabbing touch-none" : "cursor-grab touch-none"
    }),
    [handlePointerDown, handlePointerUp, isDragging]
  );

  const sheetStyle: CSSProperties = {
    height: expandedHeight,
    transform: `translateY(${translateY}px)`,
    transition: isDragging ? "none" : "transform 0.28s cubic-bezier(0.32, 0.72, 0, 1)",
    visibility: isReady ? "visible" : "hidden"
  };

  function toggleSnap() {
    setSnap((current) => (current === "collapsed" ? "expanded" : "collapsed"));
  }

  return {
    snap,
    isDragging,
    sheetStyle,
    handleProps,
    toggleSnap,
    setSnap
  };
}
