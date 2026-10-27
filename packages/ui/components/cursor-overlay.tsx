export function CursorOverlay({ x, y }: { x: number; y: number }) {
  return <span aria-hidden="true" style={{ position: "absolute", left: x, top: y, pointerEvents: "none" }}>↖</span>;
}
