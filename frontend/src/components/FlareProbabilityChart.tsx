import { useEffect, useRef } from 'react';
import type { FlareProbabilityRecord } from '../api';
import { CHART_TIME_LABELS, CHART_WINDOW_MS, RECENT_WINDOW_MS } from '../chartTime';

interface FlareProbabilityChartProps {
  points: FlareProbabilityRecord[];
}

export function FlareProbabilityChart({ points }: FlareProbabilityChartProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const context = canvas.getContext('2d');
    if (!context) return;

    function draw(canvas: HTMLCanvasElement, context: CanvasRenderingContext2D) {
      const rect = canvas.getBoundingClientRect();
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = Math.max(1, Math.floor(rect.width * dpr));
      canvas.height = Math.max(1, Math.floor(rect.height * dpr));
      const width = canvas.width;
      const height = canvas.height;
      const left = 52 * dpr;
      const right = 20 * dpr;
      const top = 16 * dpr;
      const bottom = 30 * dpr;
      const plotW = width - left - right;
      const plotH = height - top - bottom;
      const now = Date.now();
      const windowStart = now - CHART_WINDOW_MS;

      context.clearRect(0, 0, width, height);
      context.font = `${9 * dpr}px ui-monospace, SFMono-Regular, monospace`;

      [0, 25, 50, 75, 100].forEach((percent) => {
        const y = top + (1 - percent / 100) * plotH;
        context.strokeStyle = '#202634';
        context.lineWidth = dpr;
        context.beginPath();
        context.moveTo(left, y);
        context.lineTo(left + plotW, y);
        context.stroke();
        context.fillStyle = '#7f8ba3';
        context.textAlign = 'right';
        context.textBaseline = 'middle';
        context.fillText(`${percent}%`, left - 9 * dpr, y);
      });

      const recentStartX = left + ((CHART_WINDOW_MS - RECENT_WINDOW_MS) / CHART_WINDOW_MS) * plotW;
      context.fillStyle = 'rgba(85, 217, 246, 0.055)';
      context.fillRect(recentStartX, top, left + plotW - recentStartX, plotH);
      context.strokeStyle = 'rgba(85, 217, 246, 0.55)';
      context.setLineDash([4 * dpr, 4 * dpr]);
      context.beginPath();
      context.moveTo(recentStartX, top);
      context.lineTo(recentStartX, top + plotH);
      context.stroke();
      context.setLineDash([]);
      context.fillStyle = '#55d9f6';
      context.textAlign = 'center';
      context.textBaseline = 'top';
      context.fillText(
        '−300 s → now',
        recentStartX + (left + plotW - recentStartX) / 2,
        top + 5 * dpr,
      );

      context.fillStyle = '#7f8ba3';
      CHART_TIME_LABELS.forEach((label, index) => {
        const x = left + (index / (CHART_TIME_LABELS.length - 1)) * plotW;
        context.fillText(label, x, top + plotH + 9 * dpr);
      });

      const visiblePoints = points.filter((point) => {
        const timestamp = Date.parse(point.timeUT);
        return timestamp >= windowStart && timestamp <= now;
      });
      const series = [
        { key: 'R1p' as const, color: '#f4d35e' },
        { key: 'R2p' as const, color: '#ff9d5c' },
        { key: 'R3p' as const, color: '#ff5869' },
      ];
      series.forEach(({ key, color }) => {
        context.beginPath();
        let started = false;
        visiblePoints.forEach((point) => {
          const timestamp = Date.parse(point.timeUT);
          const x = left + ((timestamp - windowStart) / CHART_WINDOW_MS) * plotW;
          const y = top + (1 - point[key]) * plotH;
          if (!started) {
            context.moveTo(x, y);
            started = true;
          } else {
            context.lineTo(x, y);
          }
        });
        context.strokeStyle = color;
        context.lineWidth = 2 * dpr;
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
      className="chart-canvas probability-canvas"
      aria-label="Flare probabilities RA1, RA2, and RA3 for the last 30 minutes, with the most recent 300 seconds indicated"
    />
  );
}
