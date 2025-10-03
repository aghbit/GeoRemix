import { useState, useEffect, useCallback } from "react";

type Position = { x: number; y: number };

type UseDragOptions = {
  initialPosition?: Position;
  position?: Position;
  setPosition?: (pos: Position) => void;
  ref: React.RefObject<HTMLElement | null>;
  dragHandleRef?: React.RefObject<HTMLElement | null>;
  style?: React.CSSProperties;
  clampToViewport?: boolean;
};

export function useDrag({
  initialPosition,
  position: externalPosition,
  setPosition: externalSetPosition,
  ref,
  dragHandleRef,
  clampToViewport = true,
  style,
}: UseDragOptions) {
  const [internalPosition, setInternalPosition] = useState<Position>({
    x: initialPosition?.x || 0,
    y: initialPosition?.y || 0,
  });

  const position = externalPosition ?? internalPosition;
  const setPosition = externalSetPosition ?? setInternalPosition;

  const [isDragging, setIsDragging] = useState(false);
  const [dragStart, setDragStart] = useState<Position>({ x: 0, y: 0 });

  const clampPositionToViewport = useCallback(
    (x: number, y: number) => {
      if (!ref.current || !clampToViewport) {
        return { x, y };
      }

      const rect = ref.current.getBoundingClientRect();
      const windowWidth = Number(style?.width) || rect.width;
      const windowHeight = Number(style?.height) || rect.height;
      const viewportWidth = window.innerWidth;
      const viewportHeight = window.innerHeight;

      // Ensure window stays within viewport bounds
      const clampedX = Math.max(0, Math.min(x, viewportWidth - windowWidth));
      const clampedY = Math.max(0, Math.min(y, viewportHeight - windowHeight));

      return { x: clampedX, y: clampedY };
    },
    [ref, clampToViewport, style?.width, style?.height]
  );

  const handleMouseDown = useCallback(
    (e: MouseEvent) => {
      if (
        !ref.current ||
        (dragHandleRef?.current && !dragHandleRef.current.contains(e.target as Node))
      ) {
        return;
      }

      setIsDragging(true);
      setDragStart({
        x: e.clientX - position.x,
        y: e.clientY - position.y,
      });
    },
    [position, ref, dragHandleRef]
  );

  const handleMouseMove = useCallback(
    (e: MouseEvent) => {
      if (isDragging) {
        const newX = e.clientX - dragStart.x;
        const newY = e.clientY - dragStart.y;
        const clamped = clampPositionToViewport(newX, newY);

        setPosition(clamped);
      }
    },
    [isDragging, dragStart, clampPositionToViewport, setPosition]
  );

  const handleMouseUp = useCallback(() => setIsDragging(false), []);

  useEffect(() => {
    if (!ref.current) {
      return;
    }

    const el = ref.current;
    el.addEventListener("mousedown", handleMouseDown);
    document.addEventListener("mousemove", handleMouseMove);
    document.addEventListener("mouseup", handleMouseUp);

    return () => {
      el.removeEventListener("mousedown", handleMouseDown);
      document.removeEventListener("mousemove", handleMouseMove);
      document.removeEventListener("mouseup", handleMouseUp);
    };
  }, [handleMouseDown, handleMouseMove, handleMouseUp, ref]);

  // Clamp once on mount / position change
  useEffect(() => {
    const clamped = clampPositionToViewport(position.x, position.y);
    if (clamped.x !== position.x || clamped.y !== position.y) {
      setPosition(clamped);
    }
  }, [position, clampPositionToViewport, setPosition]);

  return {
    position,
    isDragging,
  };
}
