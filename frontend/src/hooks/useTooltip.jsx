// Per-chart tooltip hook shared by the report views.
import { useEffect, useRef, useState } from "react";

// One tooltip per chart. Content is rendered as React text, never as HTML. The frame's
// measured width lets charts draw at 1:1 scale so their text stays at the CSS size.
export function useTooltip(defaultWidth = 640) {
  const frame = useRef(null);
  const [tip, setTip] = useState(null);
  const [width, setWidth] = useState(defaultWidth);
  useEffect(() => {
    if (!frame.current || typeof ResizeObserver === "undefined") return undefined;
    const observer = new ResizeObserver(([entry]) => {
      if (entry.contentRect.width > 0) setWidth(Math.round(entry.contentRect.width));
    });
    observer.observe(frame.current);
    return () => observer.disconnect();
  }, []);
  function show(event, rows) {
    const box = frame.current?.getBoundingClientRect();
    if (!box) return;
    const point =
      event.clientX !== undefined && event.type !== "focus"
        ? { x: event.clientX, y: event.clientY }
        : (() => {
            const r = event.currentTarget.getBoundingClientRect();
            return { x: r.left + r.width / 2, y: r.top };
          })();
    setTip({ x: point.x - box.left, y: point.y - box.top, rows });
  }
  const hide = () => setTip(null);
  const handlers = (rows) => ({
    onPointerMove: (event) => show(event, rows),
    onPointerLeave: hide,
    onFocus: (event) => show(event, rows),
    onBlur: hide,
    tabIndex: 0,
  });
  const layer = tip && (
    <div className="kpi-tooltip" style={{ left: tip.x, top: tip.y }} role="status" aria-live="polite">
      {tip.rows.map((row) => (
        <div className="kpi-tooltip-row" key={row.label}>
          {row.color && <span className="kpi-tooltip-key" style={{ background: row.color }} />}
          <strong>{row.value}</strong>
          <span>{row.label}</span>
        </div>
      ))}
    </div>
  );
  return { frame, handlers, layer, width };
}
