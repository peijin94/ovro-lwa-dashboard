import { useEffect, useRef } from 'react';
import type { GoesPoint } from '../api';

interface GoesChartProps {
  points: GoesPoint[];
}

export function GoesChart({ points }: GoesChartProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const context = canvas.getContext('2d');
    if (!context) return;

    function draw(
      canvas: HTMLCanvasElement,
      context: CanvasRenderingContext2D,
    ) {
      const rect = canvas.getBoundingClientRect();
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = Math.max(1, Math.floor(rect.width * dpr));
      canvas.height = Math.max(1, Math.floor(rect.height * dpr));
      const width = canvas.width;
      const height = canvas.height;
      const left = 48 * dpr;
      const right = 20 * dpr;
      const top = 16 * dpr;
      const bottom = 30 * dpr;
      const plotW = width - left - right;
      const plotH = height - top - bottom;
      context.clearRect(0, 0, width, height);
      context.font = `${9 * dpr}px ui-monospace, SFMono-Regular, monospace`;

      const classBands = [
        { name: 'X', exponent: -4, color: '#ff6363' },
        { name: 'M', exponent: -5, color: '#ff9d5c' },
        { name: 'C', exponent: -6, color: '#f4d35e' },
        { name: 'B', exponent: -7, color: '#56d39b' },
        { name: 'A', exponent: -8, color: '#55b8f6' },
      ];
      classBands.forEach(({ name, exponent, color }) => {
        const y = top + ((-3 - exponent) / 6) * plotH;
        context.strokeStyle = '#202634';
        context.lineWidth = dpr;
        context.beginPath();
        context.moveTo(left, y);
        context.lineTo(left + plotW, y);
        context.stroke();
        context.fillStyle = color;
        context.textAlign = 'right';
        context.textBaseline = 'middle';
        context.fillText(name, left - 9 * dpr, y);
      });

      const labels = ['−300s', '−200s', '−100s', 'Now'];
      context.fillStyle = '#7f8ba3';
      context.textAlign = 'center';
      context.textBaseline = 'top';
      labels.forEach((label, index) => {
        const x = left + (index / (labels.length - 1)) * plotW;
        context.fillText(label, x, top + plotH + 9 * dpr);
      });

      const now = Date.now();
      const windowMs = 300_000;
      const windowStart = now - windowMs;
      const visiblePoints = points.filter((point) => {
        const timestamp = Date.parse(point.time);
        return timestamp >= windowStart && timestamp <= now;
      });

      const series = [
        { key: 'short' as const, color: '#55d9f6' },
        { key: 'long' as const, color: '#f4d35e' },
      ];
      series.forEach(({ key, color }) => {
        context.beginPath();
        let started = false;
        visiblePoints.forEach((point) => {
          const flux = point[key];
          if (!flux || flux <= 0) return;
          const timestamp = Date.parse(point.time);
          const x = left + ((timestamp - windowStart) / windowMs) * plotW;
          const logFlux = Math.max(-9, Math.min(-3, Math.log10(flux)));
          const y = top + ((-3 - logFlux) / 6) * plotH;
          if (!started) {
            context.moveTo(x, y);
            started = true;
          } else context.lineTo(x, y);
        });
        context.strokeStyle = color;
        context.lineWidth = 1.5 * dpr;
        context.stroke();
      });
    }

    draw(canvas, context);
    const observer = new ResizeObserver(() => draw(canvas, context));
    observer.observe(canvas);
    return () => observer.disconnect();
  }, [points]);

  return (
    <canvas
      ref={canvasRef}
      className="chart-canvas goes-canvas"
      aria-label="GOES X-ray flux for the last 300 seconds"
    />
  );
}
