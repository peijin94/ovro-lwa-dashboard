import { useEffect, useRef } from 'react';

interface LightCurveProps {
  values: number[];
}

export function LightCurve({ values }: LightCurveProps) {
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
      const left = 50 * dpr;
      const right = 16 * dpr;
      const top = 16 * dpr;
      const bottom = 30 * dpr;
      const plotW = width - left - right;
      const plotH = height - top - bottom;

      context.clearRect(0, 0, width, height);
      context.font = `${9 * dpr}px ui-monospace, SFMono-Regular, monospace`;
      context.fillStyle = '#7f8ba3';
      context.strokeStyle = '#202634';
      context.lineWidth = dpr;

      const finite = values.filter((value) => Number.isFinite(value) && value > 0);
      let min = finite.length ? Math.min(...finite) : 40;
      let max = finite.length ? Math.max(...finite) : 70;
      const padding = Math.max((max - min) * 0.15, 1);
      min -= padding;
      max += padding;

      context.textAlign = 'right';
      context.textBaseline = 'middle';
      for (let index = 0; index <= 3; index += 1) {
        const y = top + (index / 3) * plotH;
        const label = max - (index / 3) * (max - min);
        context.beginPath();
        context.moveTo(left, y);
        context.lineTo(left + plotW, y);
        context.stroke();
        context.fillText(label.toFixed(0), left - 8 * dpr, y);
      }

      context.textAlign = 'center';
      context.textBaseline = 'top';
      ['−300s', '−200s', '−100s', 'Now'].forEach((label, index) => {
        const x = left + (index / 3) * plotW;
        context.fillText(label, x, top + plotH + 9 * dpr);
      });

      if (values.length < 2) return;
      context.beginPath();
      values.forEach((value, index) => {
        const x = left + (index / (values.length - 1)) * plotW;
        const y = top + ((max - value) / (max - min)) * plotH;
        if (index === 0) context.moveTo(x, y);
        else context.lineTo(x, y);
      });
      const gradient = context.createLinearGradient(left, 0, left + plotW, 0);
      gradient.addColorStop(0, '#2e8ca7');
      gradient.addColorStop(0.65, '#59d9f5');
      gradient.addColorStop(1, '#f4d35e');
      context.strokeStyle = gradient;
      context.lineWidth = 2 * dpr;
      context.stroke();
    }

    draw(canvas, context);
    const observer = new ResizeObserver(() => draw(canvas, context));
    observer.observe(canvas);
    return () => observer.disconnect();
  }, [values]);

  return (
    <canvas
      ref={canvasRef}
      className="chart-canvas lightcurve-canvas"
      aria-label="Live 50 megahertz light curve for the last 300 seconds"
    />
  );
}
