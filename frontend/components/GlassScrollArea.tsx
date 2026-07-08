"use client";

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type MouseEvent as ReactMouseEvent,
  type ReactNode
} from "react";

type ThumbState = {
  visible: boolean;
  height: number;
  top: number;
};

type Props = {
  children: ReactNode;
  className?: string;
};

const MIN_THUMB_HEIGHT = 28;

export function GlassScrollArea({ children, className = "" }: Props) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const dragOffsetRef = useRef(0);
  const [thumb, setThumb] = useState<ThumbState>({ visible: false, height: 0, top: 0 });
  const [dragging, setDragging] = useState(false);
  const [hovered, setHovered] = useState(false);

  const updateThumb = useCallback(() => {
    const element = scrollRef.current;
    if (!element) {
      return;
    }

    const { scrollTop, scrollHeight, clientHeight } = element;
    if (scrollHeight <= clientHeight + 1) {
      setThumb({ visible: false, height: 0, top: 0 });
      return;
    }

    const thumbHeight = Math.max((clientHeight / scrollHeight) * clientHeight, MIN_THUMB_HEIGHT);
    const maxThumbTop = clientHeight - thumbHeight;
    const scrollRatio = scrollTop / (scrollHeight - clientHeight);
    const top = scrollRatio * maxThumbTop;

    setThumb({ visible: true, height: thumbHeight, top });
  }, []);

  useEffect(() => {
    const element = scrollRef.current;
    if (!element) {
      return;
    }

    updateThumb();

    const observer = new ResizeObserver(updateThumb);
    observer.observe(element);

    if (element.firstElementChild) {
      observer.observe(element.firstElementChild);
    }

    return () => observer.disconnect();
  }, [updateThumb, children]);

  useEffect(() => {
    if (!dragging) {
      return;
    }

    function onMouseMove(event: MouseEvent) {
      const element = scrollRef.current;
      if (!element) {
        return;
      }

      const trackTop = element.getBoundingClientRect().top;
      const { scrollHeight, clientHeight } = element;
      const thumbHeight = Math.max((clientHeight / scrollHeight) * clientHeight, MIN_THUMB_HEIGHT);
      const maxThumbTop = clientHeight - thumbHeight;
      const pointerY = event.clientY - trackTop - dragOffsetRef.current;
      const clampedTop = Math.min(Math.max(pointerY, 0), maxThumbTop);
      const scrollRatio = clampedTop / maxThumbTop;

      element.scrollTop = scrollRatio * (scrollHeight - clientHeight);
    }

    function onMouseUp() {
      setDragging(false);
    }

    window.addEventListener("mousemove", onMouseMove);
    window.addEventListener("mouseup", onMouseUp);

    return () => {
      window.removeEventListener("mousemove", onMouseMove);
      window.removeEventListener("mouseup", onMouseUp);
    };
  }, [dragging]);

  function handleThumbMouseDown(event: ReactMouseEvent<HTMLDivElement>) {
    event.preventDefault();
    dragOffsetRef.current = event.clientY - event.currentTarget.getBoundingClientRect().top;
    setDragging(true);
  }

  return (
    <div className={`relative min-h-0 flex-1 ${className}`}>
      <div
        ref={scrollRef}
        className="panel-scroll-hide h-full overflow-y-auto overscroll-contain py-3 pl-3 pr-8"
        onScroll={updateThumb}
      >
        {children}
      </div>

      {thumb.visible ? (
        <div
          className="pointer-events-none absolute bottom-3 right-1 top-3 w-1"
          aria-hidden="true"
        >
          <div
            className={`glass-scrollbar-thumb pointer-events-auto absolute right-0 w-1 rounded-full transition-[background,border-color,box-shadow] duration-150 ${
              dragging || hovered ? "is-active" : ""
            }`}
            style={{ height: thumb.height, transform: `translateY(${thumb.top}px)` }}
            onMouseDown={handleThumbMouseDown}
            onMouseEnter={() => setHovered(true)}
            onMouseLeave={() => setHovered(false)}
          />
        </div>
      ) : null}
    </div>
  );
}
