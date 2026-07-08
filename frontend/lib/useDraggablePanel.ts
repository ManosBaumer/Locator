"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type HTMLAttributes,
  type PointerEvent as ReactPointerEvent,
  type RefObject
} from "react";

type Position = {
  x: number;
  y: number;
};

type Options = {
  margin?: number;
  initialPosition?: Position;
};

type DragState = {
  pointerId: number;
  startX: number;
  startY: number;
  originX: number;
  originY: number;
};

function clampPosition(
  position: Position,
  panel: HTMLElement,
  margin: number
): Position {
  const rect = panel.getBoundingClientRect();
  const maxX = Math.max(margin, window.innerWidth - rect.width - margin);
  const maxY = Math.max(margin, window.innerHeight - rect.height - margin);

  return {
    x: Math.min(Math.max(margin, position.x), maxX),
    y: Math.min(Math.max(margin, position.y), maxY)
  };
}

export function useDraggablePanel(
  panelRef: RefObject<HTMLElement | null>,
  { margin = 16, initialPosition = { x: 16, y: 16 } }: Options = {}
) {
  const [position, setPosition] = useState<Position>(initialPosition);
  const [isDragging, setIsDragging] = useState(false);
  const dragStateRef = useRef<DragState | null>(null);
  const positionRef = useRef(position);

  useEffect(() => {
    positionRef.current = position;
  }, [position]);

  const clampToViewport = useCallback(
    (next: Position) => {
      const panel = panelRef.current;
      if (!panel) {
        return next;
      }
      return clampPosition(next, panel, margin);
    },
    [margin, panelRef]
  );

  useEffect(() => {
    function handleResize() {
      setPosition((current) => clampToViewport(current));
    }

    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, [clampToViewport]);

  useEffect(() => {
    if (!isDragging) {
      return;
    }

    function handlePointerMove(event: PointerEvent) {
      const dragState = dragStateRef.current;
      if (!dragState || dragState.pointerId !== event.pointerId) {
        return;
      }

      const deltaX = event.clientX - dragState.startX;
      const deltaY = event.clientY - dragState.startY;

      setPosition(
        clampToViewport({
          x: dragState.originX + deltaX,
          y: dragState.originY + deltaY
        })
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
  }, [clampToViewport, isDragging]);

  const handlePointerDown = useCallback(
    (event: ReactPointerEvent<HTMLElement>) => {
      if (event.button !== 0) {
        return;
      }

      event.preventDefault();

      dragStateRef.current = {
        pointerId: event.pointerId,
        startX: event.clientX,
        startY: event.clientY,
        originX: positionRef.current.x,
        originY: positionRef.current.y
      };

      setIsDragging(true);
      event.currentTarget.setPointerCapture(event.pointerId);
    },
    []
  );

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
      className: isDragging ? "cursor-grabbing" : "cursor-grab"
    }),
    [handlePointerDown, handlePointerUp, isDragging]
  );

  return {
    position,
    isDragging,
    panelStyle: {
      left: position.x,
      top: position.y
    } satisfies CSSProperties,
    dragHandleProps
  };
}
