import { useEffect, useRef } from "react";
import "./PointNetwork.css";

// Background point network: small points drift slowly across the page and are joined by thin lines
// when they come close. Near the cursor, points are gently pulled toward it and linked to it.
// Drawn behind the page content in the theme accent at low opacity. Reduced-motion users get a
// still network; the animation pauses while the tab is hidden.

const POINTS = 42; // number of points
const LINK_DISTANCE = 180; // px: points closer than this are joined
const CURSOR_REACH = 220; // px: points within this distance are pulled toward and linked to the cursor
const PULL = 0.015; // attraction strength toward the cursor
const FRICTION = 0.995;
const DRIFT = 0.25; // initial speed range

function cssVar(name, fallback) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
}

// Decorative animated point network drawn on a full-page background canvas (colours from the theme tokens).
function PointNetwork() {
  const canvasRef = useRef(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas.getContext("2d");
    if (!ctx) return undefined;
    const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const rgb = cssVar("--accent-rgb", "244, 81, 30");

    let width = 0;
    let height = 0;
    let points = [];
    const cursor = { x: -9999, y: -9999 };
    let frame = 0;

    function seed() {
      const dpr = Math.max(1, Math.min(window.devicePixelRatio || 1, 2));
      width = window.innerWidth;
      height = window.innerHeight;
      canvas.width = Math.floor(width * dpr);
      canvas.height = Math.floor(height * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      points = Array.from({ length: POINTS }, () => ({
        x: Math.random() * width,
        y: Math.random() * height,
        vx: (Math.random() - 0.5) * DRIFT,
        vy: (Math.random() - 0.5) * DRIFT,
        r: 1.2 + Math.random() * 1.8,
      }));
    }

    function move() {
      for (const p of points) {
        p.x += p.vx;
        p.y += p.vy;
        if (p.x < 0 || p.x > width) p.vx *= -1;
        if (p.y < 0 || p.y > height) p.vy *= -1;
        const dx = cursor.x - p.x;
        const dy = cursor.y - p.y;
        const d = Math.hypot(dx, dy);
        if (d > 0 && d < CURSOR_REACH) {
          const f = (1 - d / CURSOR_REACH) * PULL;
          p.vx += (dx / d) * f;
          p.vy += (dy / d) * f;
        }
        p.vx *= FRICTION;
        p.vy *= FRICTION;
      }
    }

    function link(x1, y1, x2, y2, alpha, lineWidth) {
      ctx.strokeStyle = `rgba(${rgb}, ${alpha})`;
      ctx.lineWidth = lineWidth;
      ctx.beginPath();
      ctx.moveTo(x1, y1);
      ctx.lineTo(x2, y2);
      ctx.stroke();
    }

    function draw() {
      ctx.clearRect(0, 0, width, height);
      for (let i = 0; i < points.length; i++) {
        for (let j = i + 1; j < points.length; j++) {
          const a = points[i];
          const b = points[j];
          const d = Math.hypot(a.x - b.x, a.y - b.y);
          if (d < LINK_DISTANCE) link(a.x, a.y, b.x, b.y, (1 - d / LINK_DISTANCE) * 0.25, 0.8);
        }
      }
      for (const p of points) {
        const d = Math.hypot(cursor.x - p.x, cursor.y - p.y);
        if (d < CURSOR_REACH) link(cursor.x, cursor.y, p.x, p.y, (1 - d / CURSOR_REACH) * 0.45, 0.6);
      }
      ctx.fillStyle = `rgba(${rgb}, 0.55)`;
      for (const p of points) {
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
        ctx.fill();
      }
    }

    function loop() {
      move();
      draw();
      frame = requestAnimationFrame(loop);
    }

    const onMove = (event) => {
      cursor.x = event.clientX;
      cursor.y = event.clientY;
    };
    const onLeave = () => {
      cursor.x = -9999;
      cursor.y = -9999;
    };
    const onResize = () => {
      seed();
      if (still) draw();
    };
    const onVisibility = () => {
      cancelAnimationFrame(frame);
      if (!document.hidden && !still) frame = requestAnimationFrame(loop);
    };

    seed();
    if (still) draw();
    else frame = requestAnimationFrame(loop);
    window.addEventListener("resize", onResize);
    window.addEventListener("pointermove", onMove, { passive: true });
    document.documentElement.addEventListener("pointerleave", onLeave);
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("resize", onResize);
      window.removeEventListener("pointermove", onMove);
      document.documentElement.removeEventListener("pointerleave", onLeave);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, []);

  return <canvas ref={canvasRef} className="point-network" aria-hidden="true" />;
}

export default PointNetwork;
